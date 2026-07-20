# Plano de Testes

Testes conteinerizados, em rede isolada (`internal: true`). Cada teste tem
critério objetivo, alinhado às métricas de aceitação da especificação original.

| # | Teste | Tipo | Procedimento | Sucesso se... |
|---|---|---|---|---|
| T1 | Propagação | Integração | Enviar 1 comando via `scripts/operator_client.py` | Todos os bots logam o `msg_id` uma única vez (sem loop) — ver `podman logs bot-N` |
| T2 | Eleição / Caos | Chaos | `./scripts/chaos.sh kill-leader-c2` (após localizar o líder nos logs) | Seguidores reelegem novo líder em ≤ 5s |
| T3 | Tolerância do alvo | Chaos | `./scripts/chaos.sh kill-target 1` e depois `kill-target 2` durante um LOADTEST | LB ejeta as falhas; requisições legítimas continuam com HTTP 200 |
| T4 | Recuperação | Chaos | Aguardar o restart automático das réplicas paradas em T3 | Réplica reinicia e é readmitida (2 health checks OK) em ≤ 15s |
| T5 | Geração de carga | Load | Disparo sincronizado via `LOADTEST` (vetor `HTTP_FLOOD`) | Telemetria do C2 líder registra degradação de latência sob carga |
| T6 | Consistência eventual | Funcional | Gerar tráfego, reiniciar uma réplica, aguardar anti-entropia | `GET /metrics` em qualquer réplica converge para o mesmo total |

## Como rodar

```bash
podman-compose up --build -d
podman logs -f c2-a   # observe a eleição inicial do líder

# abra o dashboard de observabilidade e acompanhe tudo em tempo real:
# http://localhost:8090

# dispara um teste de carga contra o LB (10.20.0.10:8080), daqui a 10s, por 15s
python3 scripts/operator_client.py <ip_de_um_c2>:9002 10.20.0.10 80 10 15

# em outro terminal, durante o teste:
./scripts/chaos.sh kill-target 1
./scripts/chaos.sh kill-target 2
```

O dashboard (`http://localhost:8090`) mostra em tempo real: latência e
estado (UP/DOWN no pool) de cada réplica, convergência do G-Counter entre
réplicas, papel de cada nó C2 (líder/seguidor) e uma linha do tempo com os
eventos discretos de ejeção, readmissão e reeleição — útil para T2, T3, T4
e T6 sem precisar ficar lendo múltiplos `podman logs` em paralelo.
