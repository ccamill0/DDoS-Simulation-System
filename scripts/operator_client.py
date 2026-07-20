#!/usr/bin/env python3
"""
operator_client.py — Interface do operador para o cluster C2.

Uso:
    python3 scripts/operator_client.py <c2_host_inicial> <target_host> \
        <target_port> <delay_s> <duration_s>

Exemplo (a partir do host, contra o compose local):
    python3 scripts/operator_client.py localhost:9002 10.20.0.10 80 10 15

O script tenta o nó C2 informado; se ele não for o líder, o próprio nó
responde qual é o líder atual e o script refaz a conexão automaticamente.
"""
import socket
import sys


def send(host: str, port: int, line: str, timeout=3.0) -> str:
    with socket.create_connection((host, port), timeout=timeout) as s:
        s.sendall(line.encode())
        s.settimeout(timeout)
        return s.recv(4096).decode().strip()


def main():
    if len(sys.argv) != 6:
        print(__doc__)
        sys.exit(1)

    c2_entry, target, port, delay, duration = sys.argv[1:6]
    host, c2_port = c2_entry.split(":")
    c2_port = int(c2_port)

    line = f"LOADTEST {target} {port} {delay} {duration}"

    for _ in range(5):
        try:
            resp = send(host, c2_port, line)
        except OSError as e:
            print(f"Falha ao conectar em {host}:{c2_port}: {e}")
            sys.exit(1)

        print(f"[{host}:{c2_port}] -> {resp}")
        if resp.startswith("NOT_LEADER"):
            # resp: "NOT_LEADER current_leader=3 host=10.20.0.23"
            parts = dict(kv.split("=") for kv in resp.split()[1:])
            if parts.get("host") in (None, "None"):
                print("Cluster C2 ainda sem líder eleito, tente novamente em instantes.")
                sys.exit(1)
            host = parts["host"]
            continue
        break


if __name__ == "__main__":
    main()
