"""
dashboard.py — Painel de observabilidade do laboratório.

Não participa da coordenação nem do ataque: apenas lê dados já expostos
pelos outros serviços (HAProxy stats, /health e /metrics dos alvos, /status
dos nós C2) e os agrega para visualização em tempo real.

Faz polling periódico de:
  - HAProxy (stats em CSV, porta 8404) -> estado UP/DOWN de cada réplica
  - cada réplica do alvo (/health, /metrics) -> latência e G-Counter
  - cada nó C2 (/status) -> papel (líder/seguidor)

Mantém um snapshot em memória + um log de eventos (transições de estado:
ejeção, readmissão, nova eleição) e expõe tudo via GET /api/state para o
frontend estático (static/index.html) consumir por polling HTTP simples
(sem websockets, de propósito, para manter o serviço simples).

Variáveis de ambiente:
  TARGETS       - "nome:host:porta,nome:host:porta,..." das réplicas do alvo
  C2_NODES      - "id:host,id:host,..." dos nós C2 (consulta em :9003/status)
  LB_STATS_URL  - URL do endpoint CSV de stats do HAProxy
  POLL_INTERVAL - segundos entre rodadas de polling (default 1.0)
  PORT          - porta HTTP do próprio dashboard (default 8090)
"""
import asyncio
import csv
import io
import os
import time
from collections import deque

import httpx
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

LB_STATS_URL = os.environ.get("LB_STATS_URL", "http://lb:8404/stats;csv")
POLL_INTERVAL = float(os.environ.get("POLL_INTERVAL", "1.0"))
HISTORY_LEN = 40
EVENT_LOG_LEN = 100


def parse_targets() -> list[tuple[str, str, int]]:
    out = []
    for entry in [t for t in os.environ.get("TARGETS", "").split(",") if t]:
        name, host, port = entry.split(":")
        out.append((name, host, int(port)))
    return out


def parse_c2_nodes() -> list[tuple[int, str]]:
    out = []
    for entry in [n for n in os.environ.get("C2_NODES", "").split(",") if n]:
        node_id, host = entry.split(":")
        out.append((int(node_id), host))
    return out


TARGET_LIST = parse_targets()
C2_LIST = parse_c2_nodes()

app = FastAPI(title="ddos-lab dashboard")

state = {
    "targets": {},   # nome -> {lb_state, reachable, latency_ms, requests_served, counts}
    "c2": {},        # node_id -> {role, leader_id, reachable}
    "history": {},   # nome -> deque[{ts, latency_ms}]
    "events": deque(maxlen=EVENT_LOG_LEN),
    "last_update": None,
}


def add_event(kind: str, message: str):
    state["events"].appendleft({"ts": time.time(), "kind": kind, "message": message})


async def fetch_lb_states(client: httpx.AsyncClient) -> dict:
    """Lê a página de stats do HAProxy em CSV; retorna {server_name: status}.
    Esta é a fonte de verdade sobre ejection/readmissão (decisão do LB,
    não uma inferência nossa)."""
    try:
        r = await client.get(LB_STATS_URL, timeout=2.0)
        r.raise_for_status()
    except httpx.HTTPError:
        return {}
    text = r.text.lstrip("# ")
    reader = csv.DictReader(io.StringIO(text))
    out = {}
    for row in reader:
        svname = row.get("svname")
        if svname and svname not in ("BACKEND", "FRONTEND"):
            out[svname] = row.get("status", "?")
    return out


async def poll_targets(client: httpx.AsyncClient, lb_states: dict):
    for name, host, port in TARGET_LIST:
        prev = state["targets"].get(name, {})
        entry = {"name": name, "lb_state": lb_states.get(name, "?")}

        try:
            t0 = time.perf_counter()
            r = await client.get(f"http://{host}:{port}/health", timeout=1.5)
            entry["latency_ms"] = round((time.perf_counter() - t0) * 1000, 2)
            h = r.json()
            entry["reachable"] = True
            entry["requests_served"] = h.get("requests_served")
        except httpx.HTTPError:
            entry["reachable"] = False
            entry["latency_ms"] = None
            entry["requests_served"] = prev.get("requests_served")

        try:
            r = await client.get(f"http://{host}:{port}/metrics", timeout=1.5)
            entry["counts"] = r.json().get("counts", {})
        except httpx.HTTPError:
            entry["counts"] = prev.get("counts", {})

        prev_lb = prev.get("lb_state")
        if prev_lb and prev_lb != entry["lb_state"]:
            if entry["lb_state"] == "DOWN":
                add_event("ejection", f"{name} foi ejetado do pool (health check falhou)")
            elif entry["lb_state"] == "UP" and prev_lb == "DOWN":
                add_event("readmission", f"{name} foi readmitido ao pool")

        state["targets"][name] = entry

        hist = state["history"].setdefault(name, deque(maxlen=HISTORY_LEN))
        hist.append({"ts": time.time(), "latency_ms": entry["latency_ms"]})


async def poll_c2(client: httpx.AsyncClient):
    for node_id, host in C2_LIST:
        prev = state["c2"].get(node_id, {})
        try:
            r = await client.get(f"http://{host}:9003/status", timeout=1.5)
            s = r.json()
            entry = {
                "node_id": node_id,
                "role": s.get("role"),
                "leader_id": s.get("leader_id"),
                "reachable": True,
            }
        except httpx.HTTPError:
            entry = {
                "node_id": node_id,
                "role": prev.get("role"),
                "leader_id": prev.get("leader_id"),
                "reachable": False,
            }

        if entry["role"] == "LEADER" and prev.get("role") != "LEADER":
            add_event("election", f"c2 nó {node_id} tornou-se LÍDER")

        state["c2"][node_id] = entry


async def poll_once(client: httpx.AsyncClient):
    lb_states = await fetch_lb_states(client)
    await poll_targets(client, lb_states)
    await poll_c2(client)
    state["last_update"] = time.time()


async def poll_loop():
    async with httpx.AsyncClient() as client:
        while True:
            try:
                await poll_once(client)
            except Exception as e:
                # nunca deixa uma falha pontual (ex.: peer temporariamente
                # fora do ar) derrubar o loop de observabilidade
                print(f"[dashboard] erro no polling: {e}")
            await asyncio.sleep(POLL_INTERVAL)


@app.on_event("startup")
async def startup():
    asyncio.create_task(poll_loop())


@app.get("/api/state")
async def api_state():
    return {
        "targets": state["targets"],
        "c2": state["c2"],
        "history": {k: list(v) for k, v in state["history"].items()},
        "events": list(state["events"]),
        "last_update": state["last_update"],
    }


app.mount("/", StaticFiles(directory="static", html=True), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8090")))
