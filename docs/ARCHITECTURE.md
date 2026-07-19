# Arquitetura

## Visão geral

```
OPERADOR --(LOADTEST <alvo> <delay> <duração>)--> CLUSTER C2 (líder via Bully)
                                                         |
                                            injeta JSON em 1 bot aleatório
                                                         v
                                    BOTNET P2P (malha, Gossip Protocol)
                                                         |
                                   carga HTTP sincronizada (barreira de tempo)
                                                         v
                         LOAD BALANCER (HAProxy) -- health check / ejection
                                    /            |            \
                              target-1       target-2       target-3
                        (réplicas ativo-ativo, G-Counter CRDT via gossip)
```

## Componentes

| Componente | Arquivo | Responsabilidade |
|---|---|---|
| Alvo (réplica) | `target/target.py` | Serve HTTP, expõe `/health` e `/metrics`, replica contador via anti-entropia |
| Load Balancer | `lb/haproxy.cfg` | Balanceia, checa saúde, ejeta/readmite réplicas |
| Nó C2 | `c2/c2.py` | Heartbeat, eleição Bully, telemetria, injeção de comando, expõe `/status` (leitura) |
| Bot | `bot/bot.py` | Gossip, sharding, barreira de sincronização, geração de carga |
| Dashboard | `dashboard/dashboard.py` | Observabilidade: agrega `/health`, `/metrics`, stats do LB e `/status` do C2 em tempo real |
| Orquestrador | `podman-compose.yml` | Sobe a topologia com IPs estáticos e rede isolada |

## Observabilidade (`dashboard/`)

Serviço somente-leitura, sem participação na coordenação nem no ataque. Faz
polling HTTP a cada ~1s de três fontes já existentes no sistema:

- **HAProxy** (`GET /stats;csv` na porta 8404) — fonte de verdade sobre
  ejeção/readmissão de réplicas (decisão do próprio LB).
- **Cada réplica do alvo** (`GET /health`, `GET /metrics`) — latência e o
  mapa do G-Counter, usado para visualizar a convergência da replicação.
- **Cada nó C2** (`GET /status`, novo endpoint HTTP somente-leitura em
  `:9003`) — papel atual (`LEADER`/`FOLLOWER`) e líder reconhecido.

O backend (`FastAPI`) mantém um snapshot em memória, deriva eventos
discretos comparando o estado anterior com o atual (ejeção, readmissão,
nova eleição) e expõe tudo em `GET /api/state`. O frontend
(`dashboard/static/index.html`) é HTML/CSS/JS puro — sem bibliotecas
externas — porque a rede do laboratório é `internal: true` e não tem rota
para CDNs; as sparklines de latência são desenhadas manualmente em SVG.

Acesso: `http://localhost:8090` (mesma ressalva de publicação de porta em
rede `internal: true` que se aplica ao `lb`, ver README).

## Mensagens (JSON)

**Heartbeat C2 (UDP :9000)**
```json
{ "type": "HEARTBEAT", "node_id": 3, "role": "LEADER", "ts": 1782000000.123 }
```

**Eleição Bully (TCP :9001)**
```json
{ "type": "ELECTION", "from_id": 2 }
{ "type": "OK", "from_id": 3 }
{ "type": "COORDINATOR", "leader_id": 3 }
```

**Comando de teste de carga (C2 → bot de entrada → gossip, TCP :7000)**
```json
{
  "msg_id": "550e8400-e29b-41d4-a716-446655440000",
  "type": "LOADTEST",
  "target": "10.20.0.10",
  "target_port": 80,
  "execute_at": 1782000060,
  "duration_s": 15,
  "sharding_rules": { "0": "HTTP_FLOOD", "1": "SYN_FLOOD", "2": "SLOWLORIS" },
  "ttl": 6,
  "issued_by": 3
}
```

**Anti-entropia do contador (G-Counter, HTTP `POST /metrics/sync`)**
```json
{ "target-1": 4021, "target-2": 5110, "target-3": 1162 }
```

## Decisões-chave (resumo)

- **CAP**: plano de dados (alvo) = **AP**; plano de controle (C2) = brevemente
  CP durante uma eleição (janela de segundos).
- **Replicação**: ativo-ativo + anti-entropia por gossip, G-Counter CRDT
  (merge = máximo por chave — comutativo, associativo, idempotente).
- **Tolerância a falhas**: crash, omissão e temporal; bizantino fora de
  escopo (rede fechada e de confiança). N = f+1 = 3 nós tolera f = 2 falhas
  por cluster.
- **Eleição de líder**: Bully — simples e adequado a um grupo pequeno numa
  rede confiável.
- **Sincronização**: relógio físico + barreira de tempo (a causalidade não
  importa; importa o instante absoluto comum).

Para a discussão completa de cada decisão (incluindo as trocas consideradas,
como Raft vs. Bully, ou consistência forte vs. eventual), ver o documento de
especificação original do projeto.
