"""
target.py — Serviço alvo (réplica) do plano defensivo.

Responsabilidade única: servir HTTP, expor /health e /metrics, e manter um
contador de requisições replicado entre réplicas via anti-entropia (gossip)
usando um G-Counter CRDT (Grow-only Counter).

Variáveis de ambiente:
  REPLICA_ID   - identificador desta réplica (ex.: "target-1")
  PORT         - porta HTTP (default 8000)
  PEERS        - lista separada por vírgula de peers "host:port" para anti-entropia
  GOSSIP_EVERY - intervalo em segundos entre rodadas de anti-entropia (default 3)
"""
import asyncio
import os
import random
import time
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

REPLICA_ID = os.environ.get("REPLICA_ID", "target-unknown")
PORT = int(os.environ.get("PORT", "8000"))
PEERS = [p for p in os.environ.get("PEERS", "").split(",") if p]
GOSSIP_EVERY = float(os.environ.get("GOSSIP_EVERY", "3"))

START_TS = time.time()

# ---------------------------------------------------------------------------
# G-Counter CRDT: mapa replica_id -> contagem local.
# merge() é o máximo por chave: comutativo, associativo, idempotente.
# ---------------------------------------------------------------------------
class GCounter:
    def __init__(self, my_id: str):
        self.my_id = my_id
        self.counts: dict[str, int] = {my_id: 0}
        self._lock = asyncio.Lock()

    async def increment(self):
        async with self._lock:
            self.counts[self.my_id] = self.counts.get(self.my_id, 0) + 1

    async def merge(self, remote: dict):
        async with self._lock:
            for k, v in remote.items():
                self.counts[k] = max(self.counts.get(k, 0), v)

    async def snapshot(self) -> dict:
        async with self._lock:
            return dict(self.counts)

    async def total(self) -> int:
        async with self._lock:
            return sum(self.counts.values())


counter = GCounter(REPLICA_ID)


async def anti_entropy_loop():
    """A cada GOSSIP_EVERY segundos, envia o mapa local a um peer aleatório
    e faz merge da resposta (troca bidirecional)."""
    if not PEERS:
        return
    async with httpx.AsyncClient(timeout=2.0) as client:
        while True:
            await asyncio.sleep(GOSSIP_EVERY + random.uniform(0, 0.5))
            peer = random.choice(PEERS)
            try:
                payload = await counter.snapshot()
                resp = await client.post(f"http://{peer}/metrics/sync", json=payload)
                if resp.status_code == 200:
                    await counter.merge(resp.json())
            except (httpx.ConnectError, httpx.TimeoutException, httpx.ReadError):
                # Peer indisponível (crash/omissão/temporal) — consistente com o
                # modelo de falhas do projeto; simplesmente tenta de novo depois.
                pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(anti_entropy_loop())
    yield
    task.cancel()


app = FastAPI(title=f"target ({REPLICA_ID})", lifespan=lifespan)


@app.middleware("http")
async def count_requests(request: Request, call_next):
    response = await call_next(request)
    if request.url.path not in ("/health", "/metrics", "/metrics/sync"):
        await counter.increment()
    return response


@app.get("/")
async def root():
    return {"service": "target", "replica_id": REPLICA_ID, "message": "ok"}


@app.get("/health")
async def health():
    start = time.perf_counter()
    total = await counter.total()
    latency_ms = round((time.perf_counter() - start) * 1000, 2)
    return {
        "status": "ok",
        "replica_id": REPLICA_ID,
        "latency_ms": latency_ms,
        "requests_served": total,
        "uptime_s": round(time.time() - START_TS, 1),
    }


@app.get("/metrics")
async def metrics():
    snap = await counter.snapshot()
    return {"replica_id": REPLICA_ID, "counts": snap, "total": sum(snap.values())}


@app.post("/metrics/sync")
async def metrics_sync(remote: dict):
    """Endpoint de anti-entropia: recebe o mapa de outra réplica, faz merge
    (máximo por chave) e devolve o próprio mapa já atualizado."""
    await counter.merge(remote)
    return JSONResponse(await counter.snapshot())


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)
