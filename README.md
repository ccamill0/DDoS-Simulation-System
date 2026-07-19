# Laboratório de Sistemas Distribuídos: Ataque Coordenado × Defesa Resiliente

Laboratório conteinerizado (Podman) para a disciplina de Sistemas Distribuídos,
demonstrando coordenação descentralizada (gossip, eleição de líder, barreira
de sincronização) confrontada por uma defesa distribuída (réplicas
ativo-ativo atrás de um Load Balancer com health check, ejection e
auto-restart).

> ⚠️ **Leia `docs/SAFETY_NOTES.md` antes de tudo.** Este repositório
> implementa a arquitetura de coordenação distribuída por completo, mas o
> vetor de carga executado de fato é limitado a requisições HTTP válidas
> (tecnicamente equivalente a uma ferramenta de load-testing distribuída).
> Técnicas de exaustão de protocolo (SYN flood via raw sockets, Slowloris)
> aparecem na arquitetura (sharding) mas não têm execução funcional — ver a
> justificativa completa no documento citado.

## Estrutura

```
ddos-lab/
├── target/            # réplica do serviço alvo (FastAPI) + CRDT G-Counter
├── lb/                 # configuração do HAProxy (health check, ejection)
├── c2/                 # nó do cluster de comando: Bully, heartbeat, telemetria
├── bot/                 # nó P2P: gossip, sharding, barreira, geração de carga
├── dashboard/           # painel de observabilidade em tempo real (somente leitura)
├── scripts/             # cliente do operador + utilitários de chaos testing
├── tests/               # plano de testes (T1–T6)
├── docs/
│   ├── ARCHITECTURE.md
│   └── SAFETY_NOTES.md
└── podman-compose.yml
```

## Como rodar

Pré-requisitos: Podman + `podman-compose`.

```bash
podman-compose up --build -d
podman ps
podman logs -f c2-a       # acompanhe heartbeats e a eleição inicial de líder
```

Disparar um teste de carga sincronizado contra o alvo (via LB):

```bash
# LOADTEST <target_host> <target_port> <delay_s> <duration_s>
python3 scripts/operator_client.py <ip-de-um-c2>:9002 10.20.0.10 80 10 15
```

Ver a saúde do pool no HAProxy: `http://localhost:8404/stats` (se a
publicação de porta funcionar com `internal: true` no seu runtime; senão,
`podman exec -it lb sh` e consulte localmente).

Provocar falhas (chaos testing):

```bash
./scripts/chaos.sh kill-target 1
./scripts/chaos.sh kill-target 1 2
```

Ver `tests/test_plan.md` para o roteiro completo de testes e critérios de
sucesso, e `docs/ARCHITECTURE.md` para os esquemas de mensagem e as decisões
de projeto (CAP, replicação, tolerância a falhas, eleição).

## Escopo

Este projeto foi construído a partir de uma especificação técnica completa
(inclusa como referência do trabalho). A implementação aqui presente cobre:

- ✅ Malha P2P com Gossip Protocol (deduplicação por `msg_id`)
- ✅ Cluster C2 com eleição de líder (Bully) e heartbeats
- ✅ Sincronização por barreira de relógio físico
- ✅ Sharding ofensivo por IP (RF02)
- ✅ Alvo replicado (N=3) atrás de LB com health check, ejection e restart
- ✅ Replicação ativo-ativo com G-Counter CRDT (consistência eventual)
- ✅ Vetor de carga `HTTP_FLOOD` funcional
- 🚫 Vetores `SYN_FLOOD` / `SLOWLORIS` como stubs (arquitetura presente,
  execução não implementada — ver `docs/SAFETY_NOTES.md`)

## Uso

Educacional. Roda em rede isolada (`internal: true` no compose) e ataca
apenas containers criados pelo próprio projeto.
