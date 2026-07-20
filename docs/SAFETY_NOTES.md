# Notas de Segurança e Escopo

Este documento existe para deixar explícito — para o professor, para quem revisar
o repositório e para vocês mesmos — exatamente onde este projeto traçou uma linha,
e por quê.

## O que foi implementado por completo

- **Plano defensivo inteiro**: réplicas ativo-ativo, HAProxy com health check
  ativo/ejection/readmissão, auto-restart, replicação G-Counter CRDT por
  anti-entropia.
- **Toda a infraestrutura de coordenação do plano ofensivo**: malha P2P com
  Gossip Protocol (deduplicação por `msg_id`, propagação epidêmica), cluster
  C2 com eleição de líder (Bully), heartbeats UDP, telemetria, sharding por
  IP, barreira de sincronização por relógio físico.
- **Um vetor de carga real**: `HTTP_FLOOD`, implementado como rajada de
  requisições GET concorrentes e válidas — tecnicamente a mesma técnica usada
  por ferramentas padrão de *load testing* (`ab`, `wrk`, `k6`, Locust em modo
  distribuído). Isso é suficiente para demonstrar RF01–RF09, o Teorema CAP em
  ação e a tolerância a falhas do alvo sob carga real.

## O que foi deixado como stub (sem execução real)

- **`SYN_FLOOD`**: normalmente implementado manipulando *raw sockets* para
  abrir handshakes TCP incompletos em massa, exaurindo a tabela de conexões
  do alvo.
- **`SLOWLORIS`**: normalmente implementado mantendo conexões HTTP
  deliberadamente incompletas e lentas, exaurindo o pool de *workers* do
  servidor.

Em `bot.py`, esses dois vetores **são reconhecidos pela lógica de sharding**
(a atribuição por IP acontece normalmente, `RF02` continua satisfeito), mas a
função de execução é um stub que apenas loga o evento — nenhum socket cru é
aberto, nenhuma conexão é deliberadamente presa.

### Por que esse recorte, já que tudo roda numa rede isolada?

Porque o artefato de código não sabe, e não pode saber, que está "confinado".
Um `bot.py` com SYN flood ou Slowloris genuinamente implementados é, em
termos técnicos, uma ferramenta de DDoS funcional e portátil: a diferença
entre rodar contra `10.20.0.10` (o container de vocês) e rodar contra
qualquer IP público é trocar uma string na configuração. O isolamento de rede
do laboratório protege o *ambiente de execução durante a demonstração*, mas
não muda o que o código, uma vez escrito e versionado num repositório
git/GitHub, é capaz de fazer se copiado ou reaproveitado fora dele.

Por isso o corte foi feito na camada de **implementação do vetor**, não na
arquitetura de coordenação: gossip, eleição de líder, sharding e barreira de
sincronização são padrões genéricos de sistemas distribuídos (usados em
sistemas como Cassandra, Consul, etc.) e continuam totalmente funcionais e
documentados — é isso, aliás, que a disciplina de Sistemas Distribuídos avalia.

## Para o relatório

Vocês podem (e devem) discutir os três vetores — inclusive `SYN_FLOOD` e
`SLOWLORIS` — na seção de análise/relatório, citando a literatura (RFC dos
protocolos envolvidos, o próprio texto da especificação). O que este
repositório não faz é fornecer uma implementação funcional de exaustão de
protocolo pronta para uso.

## Nota de adaptação: porta do Load Balancer (80 → 8080)

A especificação original (§13.2) lista a porta **80** para o Load Balancer.
Neste repositório o HAProxy escuta na **8080** internamente. Isso não é uma
mudança de arquitetura — é uma adaptação prática: containers rootless (o
padrão do Podman Desktop, especialmente em Windows/WSL2) não conseguem abrir
portas privilegiadas (< 1024) sem configuração extra de capabilities no
kernel do host, algo que varia bastante entre ambientes e nem sempre é
possível sem acesso root à VM. Trocar para 8080 elimina esse problema de
forma portátil, sem exigir nenhuma configuração adicional de quem for rodar
o laboratório. Vale mencionar essa adaptação (e o motivo) no relatório, já
que é uma decisão de implantação real, não um detalhe de acaso.
