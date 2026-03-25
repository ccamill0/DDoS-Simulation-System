# DDoS Simulation System

## 1. Definição do Projeto

O **Sistema de Simulação de Ataques DDoS** é um laboratório prático, controlado e conteinerizado, focado na intersecção entre **Segurança Ofensiva**, **Redes de Computadores** e **Sistemas Distribuídos Avançados**.

Enquanto um ataque de Negação de Serviço (DoS) tradicional parte de uma única máquina, o **DDoS (*Distributed Denial of Service*)** consiste em uma ofensiva massiva e coordenada proveniente de múltiplas fontes simultâneas

Para emular esse cenário realista, o projeto reproduz o comportamento de uma ***Botnet*** moderna (uma rede de computadores zumbis) altamente autônoma e descentralizada.

Além de explorar técnicas de evasão (falsificação de cabeçalhos) e as diferenças entre ataques por exaustão de volume (UDP/HTTP Flood) e exaustão de recursos (Slowloris), o sistema demonstra na prática os seguintes conceitos de engenharia distribuída:

- **Tolerância a Falhas no Controlador (C2):** Implementação de um cluster de Comando e Controle com eleição de líder, evitando pontos únicos de falha (*Single Point of Failure*).
- **Coordenação P2P (*Gossip Protocol*):** Abandono da topologia estrela convencional em favor de uma rede *Peer-to-Peer*, onde os bots propagam comandos de ataque entre si de forma epidêmica.
- **Particionamento de Tarefas (*Sharding* Ofensivo):** Divisão inteligente da carga de trabalho, onde diferentes nós assumem vetores de ataque distintos baseados em regras lógicas condicionais atreladas aos seus IPs.
- **Sincronização de Relógios Distribuídos:** Utilização de uma barreira de tempo (*Timestamp Sync*) para garantir que a rede P2P, mesmo com latências de propagação, dispare os pacotes contra o alvo no exato mesmo milissegundo.

```markdown
ddos_sim_redteam/
│
├── c2.py               # Nó do Cluster C2: implementa Eleição de Líder, Telemetria e injeta o comando na rede P2P
├── bot.py              # Bot P2P: propaga comandos via Gossip Protocol, aplica regras de Sharding e sincroniza o ataque
├── target.py           # Servidor alvo: API web genérica (vítima) focada apenas em tentar se manter no ar
│
├── requirements.txt    # Dependências mínimas do experimento
├── podman-compose.yml  # Orquestra o Cluster C2 (Tolerância a Falhas), Target e a rede P2P de Bots simultaneamente
└── README.md           # Explicações, arquitetura distribuída e instruções de execução
```

## 2. Processo Estrutural (O Ciclo de Vida do Sistema)

O funcionamento do projeto segue um fluxo cronológico focado na orquestração distribuída, propagação de mensagens e medição do impacto do ataque.

**Fase 1: Inicialização e Infraestrutura Distribuída**

- O processo começa no terminal com o Podman. Ao executar o `podman-compose`, o sistema cria uma rede virtual isolada.
- Dentro dessa rede, nascem os contêineres: um atua como **Servidor Alvo**, um grupo de contêineres atua como um **Cluster C2 (Coordenadores)**, e múltiplos contêineres idênticos atuam como **Bots**. Todos recebem IPs virtuais fechados.

**Fase 2: Consenso, Teia P2P e Telemetria**

- Assim que o Cluster C2 "nasce", os nós trocam mensagens de *heartbeat* e realizam uma **Eleição de Líder**. O Líder eleito inicia a *thread* de Telemetria, "pingando" o Alvo a cada 2 segundos e plotando a saúde no terminal (ex: *Alvo Saudável - Resposta em 20ms*).
- Em paralelo, os Bots entram em ação. Em vez de sobrecarregar o C2, eles formam uma **Rede P2P**, abrindo conexões apenas com seus nós vizinhos diretos.

**Fase 3: O Comando de Ataque e Injeção (Orquestração C2)**

- O operador da ofensiva digita o comando no C2 Líder, definindo o alvo, as regras de particionamento e um horário exato no futuro para o ataque (ex: `ATTACK 192.168.1.10 SYNC 1711384500`).
- O C2 empacota essa ordem em um *Payload JSON* contendo as regras de *Sharding* e o *Timestamp* de execução. Em seguida, ele **injeta** essa mensagem em apenas um nó aleatório da botnet (Nó de Entrada).

**Fase 4: Propagação Epidêmica e Sincronização (*Gossip Protocol*)**

- O Nó de Entrada recebe o JSON e aplica o **Protocolo de Fofoca (*Gossip Protocol*)**, repassando a ordem para seus vizinhos, que repassam para outros vizinhos. Em milissegundos, toda a botnet recebe o comando.
- Os bots interpretam a carga, preparam seus *sockets*, mas não atacam. Eles aguardam em uma **Barreira de Sincronização**, monitorando o relógio local até atingirem o *Timestamp* exato ditado pelo C2.

**Fase 5: Execução Particionada (*Sharding* Ofensivo)**

- No milissegundo exato combinado, a botnet inteira dispara simultaneamente.
- Em vez de todos fazerem a mesma coisa, a rede aplica as regras de **Sharding** contidas no JSON: com base no próprio IP (ex: ímpar ou par), uma parte da botnet inunda a rede (UDP Flood), outra gera requisições falsificadas (HTTP Flood) e outra prende conexões lentas (Slowloris), maximizando o dano através da divisão de trabalho.

**Fase 6: Medição de Impacto e Resiliência**

- Enquanto o ataque multivetorial ocorre, o operador observa a telemetria do C2 Líder registrar a queda do alvo (de 20ms para *Timeout* ou *Connection Refused*).
- Se, durante o ataque, o C2 Líder for derrubado, os nós Seguidores detectam a falha, elegem um novo Líder em tempo real e retomam a telemetria, provando a **Tolerância a Falhas** do sistema distribuído.

<img width="1147" height="865" alt="Captura de Tela (951)" src="https://github.com/user-attachments/assets/b07e1219-05c4-42a6-bc83-e6a8d7f1c5ae" />


## 3. Roteiro de Estudos

Para dominar e defender a arquitetura avançada deste projeto, o aluno deve focar seus estudos na intersecção entre infraestrutura de redes, táticas ofensivas e algoritmos clássicos de sistemas distribuídos:

### 1. Sistemas Distribuídos e Arquitetura Descentralizada

- **Tolerância a Falhas e Eleição de Líder:** Abandono do modelo *Master-Worker* tradicional. Estude como clusters mantêm consenso e elegem um novo coordenador caso o nó principal caia (conceitos simplificados dos algoritmos *Raft* ou *Bully*).
- **Redes P2P e Protocolo de Fofoca (*Gossip Protocol*):** Como contornar gargalos de rede eliminando a comunicação centralizada. Estude como a propagação epidêmica de mensagens (*Broadcast* Descentralizado) infecta a rede em tempo logarítmico.
- **Sincronização de Relógios e Barreira Distribuída:** O desafio de fazer máquinas com latências diferentes executarem uma ação no exato mesmo milissegundo usando *Timestamping* no futuro (Barreira Lógica).
- **Particionamento de Tarefas (*Sharding*):** Como dividir uma grande carga de trabalho ofensiva entre múltiplos nós baseando-se em regras de roteamento (ex: *hashes* ou IPs).
- **Concorrência em Python:** A espinha dorsal do *bot*. Estude *Threading* e o módulo `socket`. Um nó precisa escutar fofocas, manter a barreira de tempo e disparar múltiplas *threads* de ataque simultaneamente.

### 2. Redes de Computadores e Protocolos de Baixo Nível

- **Modelo TCP/IP e Sockets:** O uso de portas e IPs para comunicação crua. Entenda o fluxo dos Sockets TCP (`bind`, `listen`, `accept`, `connect`) para a fofoca P2P e a eleição do C2.
- **TCP vs. UDP:** A diferença vital entre protocolos orientados a conexão (*handshake* de 3 vias) e *connectionless* (dispara e esquece).
- **Protocolo HTTP:** Como estruturar uma requisição `GET` nativa a nível de *bytes* e o que é o cabeçalho *User-Agent*.

### 3. Segurança Ofensiva e Vetores de Ataque (Red Team)

- **Anatomia de uma Botnet:** Entenda o ciclo de vida real: um invasor cria uma rede de hosts infectados (zumbis). Esses computadores examinam a rede e infectam mais hosts. Quando a infraestrutura está pronta, os manipuladores (C2) instruem a rede para executar o DDoS.
- **Ataques Volumétricos (UDP/HTTP Flood):** Como o foco é esgotar a banda da rede ou a capacidade de processamento imediato do alvo com força bruta distribuída.
- **Exaustão de Recursos/Estado (Slowloris):** Estude como servidores web lidam com conexões simultâneas (limites de *threads* ou *workers*). Entenda como enviar requisições HTTP incompletas e muito lentas prende os recursos da vítima de forma letal e silenciosa.
- **Evasão Básica:** A teoria por trás da randomização de *payloads* e falsificação de cabeçalhos para contornar proteções simples baseadas em assinaturas estáticas.

### 4. Orquestração com Podman

- **Contêineres OCI:** Entenda como empacotar scripts Python e suas dependências em contêineres usando `Containerfile` ou `Dockerfile`.
- **Daemonless e Rootless:** A diferença arquitetural de segurança do Podman (que não possui um serviço central rodando como *root*) em comparação ao Docker.
- **Redes Virtuais (Podman Compose):** Como desenhar um arquivo `.yaml` que levanta o Cluster C2, o Alvo e a Botnet P2P em um ambiente seguro, estritamente isolado da internet real, definindo IPs estáticos para o laboratório.

## 4. Plano e Roteiro de Desenvolvimento

Devido à alta complexidade inerente à programação de Sistemas Distribuídos (condições de corrida, *deadlocks* e dessincronização), a construção deste software foi planejada em **fases incrementais e modulares**.

Cada fase entrega um produto funcional por si só. Dessa forma, garante-se que a arquitetura escale com segurança, permitindo testes isolados de infraestrutura antes de avançar para a próxima etapa.

### Fase 1: Fundação e A Rede P2P (*Gossip Protocol*)

O objetivo inicial é criar a vítima (o alvo) e estabelecer a comunicação descentralizada entre os bots, garantindo que uma ordem se propague pela rede sem *loops* infinitos.

- **Passo 1.1 - O Saco de Pancadas (`target.py`):** Criar um servidor web genérico e simples (usando *FastAPI* ou *Flask*) apenas para existir na rede e registrar requisições. Ele será a nossa métrica de sucesso.
- **Passo 1.2 - O Nascimento do Nó P2P (`bot.py`):** Criar o esqueleto do bot. Ele deve ser capaz de abrir uma porta TCP para ouvir mensagens, enquanto simultaneamente mantém a capacidade de enviar dados. (Exige *Multithreading* básico).
- **Passo 1.3 - Topologia e Vizinhança:** Definir no `podman-compose.yml` os IPs estáticos dos bots. Programar cada `bot.py` para conhecer o IP de 2 ou 3 vizinhos diretos, formando uma malha (*mesh*).
- **Passo 1.4 - A Fofoca (Gossip):** Criar a lógica de propagação. O bot recebe um JSON, verifica o `msg_id` (para garantir que não é uma mensagem repetida) e repassa para seus vizinhos mapeados.

### Fase 2: Inteligência Ofensiva (Sincronização e *Sharding*)

Com a rede conversando entre si, é hora de "armar" a botnet, ensinando-a a extrair as regras táticas do JSON e a atacar o alvo.

- **Passo 2.1 - O Gatilho e as Armas:** Programar as funções de ataque dentro do `bot.py` (A função de *HTTP Flood*, a de *UDP Flood* e o *Slowloris*).
- **Passo 2.2 - Particionamento de Tarefas (*Sharding*):** Fazer o bot ler o bloco `sharding_rules` do JSON. Baseado no último octeto do seu próprio IP (par ou ímpar), o bot seleciona qual das três funções de ataque ele vai carregar na memória.
- **Passo 2.3 - A Barreira de Tempo (*Sync*):** Fazer o bot ler o bloco `sync` do JSON. Implementar um *loop* de espera que compara o relógio local da máquina com o *Timestamp* recebido.
- **Passo 2.4 - Fogo Centralizado:** Testar a propagação. Injetar manualmente um JSON na rede e observar todos os contêineres disparando as *threads* de ataque contra o `target.py` no exato mesmo segundo, com vetores diferentes.

### Fase 3: O Cérebro Resiliente (Cluster C2 e Eleição de Líder)

Com a botnet autônoma e mortal, a fase final substitui o operador manual por um cluster inteligente e tolerante a falhas.

- **Passo 3.1 - A Gênese do C2 (`c2.py`):** Criar o nó controlador que vai gerar o JSON com o *msg_id* único, definir a regra matemática do *Sharding*, carregar o *Timestamp* atual + X segundos e repassar para o Nó de Entrada da Botnet.
- **Passo 3.2 - O Cluster e os *Heartbeats*:** Subir 3 cópias do C2 no *Podman Compose*. Programar para que eles troquem pulsos de vida (UDP em rede fechada) a cada segundo para provarem que estão ativos.
- **Passo 3.3 - Eleição de Líder (Consenso):** Implementar a lógica de que apenas um C2 é o "Líder". Se os "Seguidores" pararem de receber o *heartbeat* do Líder (ex: derrubamos o contêiner de propósito), eles comparam seus IDs e o maior assume o controle da Botnet.
- **Passo 3.4 - Telemetria em Tempo Real:** Acoplar no Líder uma *thread* separada que faz *Ping* ou requisições de saúde ao `target.py`, exibindo a latência no terminal do Operador, finalizando o ciclo visual do Red Team.

## Questionário

1. **Dos modelos estudados algum se encaixa?(Em camadas, micro serviços, pu sub, P2P(estruturado/não-estruturado)**

O projeto utiliza uma arquitetura híbrida, combinando dois modelos clássicos de Sistemas Distribuídos:

- **Para a Botnet: P2P Não-Estruturado (*Unstructured Peer-to-Peer*):** A rede de bots não possui uma topologia rígida de roteamento (como uma *Distributed Hash Table - DHT*). Em vez disso, ela forma uma malha (*mesh*) onde cada nó conhece apenas um pequeno subconjunto de vizinhos aleatórios. Esse é o modelo perfeito para aplicar o *Gossip Protocol* (Protocolo de Fofoca), pois permite alta escalabilidade e resiliência sem a necessidade de manter uma estrutura complexa de endereçamento.
- **Para o Comando e Controle (C2): Cluster com Consenso (Tolerância a Falhas):** O C2 deixou de ser um modelo centralizado cliente-servidor (ou *Master-Worker* simples) para se tornar um grupo de nós que utilizam um algoritmo de Eleição de Líder e troca de *Heartbeats* para manter o estado do sistema.

2. **Arquitetura de SW interna**

Internamente, os scripts (especialmente o `bot.py` e o `c2.py`) utilizarão uma **Arquitetura Orientada a Eventos e baseada em Concorrência (Multithreading/Assíncrona)**.

- **No Bot:** A arquitetura interna será dividida em *Threads* independentes.
    - Uma *thread* rodará um servidor TCP constante (ouvindo fofocas dos vizinhos).
    - Outra *thread* cuidará do *Loop* de Sincronização (esperando o *timestamp* do ataque).
    - E múltiplas *threads* efêmeras serão criadas no momento exato do ataque para disparar os pacotes (HTTP/UDP/Slowloris) sem travar a escuta de novos comandos.
- **No C2:** Teremos *threads* separadas para trocar pulsos de vida com os outros C2, para ler os comandos do operador e para realizar a telemetria do alvo.

3. **Como o sistema será testado?**

O sistema será testado de forma conteinerizada (usando o `podman-compose`), garantindo que a rede seja isolada e segura. Aplicaremos três tipos práticos de testes de Sistemas Distribuídos:

- **Teste de Propagação (Integração):** Injetar um comando JSON no "Nó de Entrada" e verificar nos logs dos contêineres se a mensagem se propagou por todos os bots em tempo logarítmico, sem gerar *loops* infinitos (verificando o `msg_id`).
- **Teste de Engenharia do Caos (*Chaos Engineering*):** Durante a execução pacífica da rede, o operador executará um `podman stop` no contêiner do C2 Líder. O teste será considerado um sucesso se os C2 Seguidores detectarem a queda e elegerem um novo Líder automaticamente em poucos segundos.
- **Teste de Estresse/Carga (*Load Testing*):** Com a rede sincronizada, os bots farão o disparo unificado. O sucesso será medido pela telemetria do C2 registrando a degradação do `target.py` (tempo de resposta aumentando de milissegundos para *Timeout*).
  
4. **Faz sentido usar algum tipo de middleware?**

**Neste contexto específico (Segurança Ofensiva / Red Team), NÃO faz sentido usar um *middleware* comercial tradicional (como RabbitMQ, Apache Kafka ou gRPC).**

- **A Justificativa:** O projeto simula a infecção por malwares e a criação de uma *Botnet*. Em cenários reais, um malware precisa ser extremamente leve (alguns kilobytes), furtivo e rodar nativamente no sistema operacional da vítima. Exigir que um nó infectado instale um *broker* de mensagens pesado ou dependa de um servidor central de mensageria quebra o realismo do ataque e introduz um ponto único de falha.
- **A Nossa Solução:** Em vez de usar um *middleware* de terceiros, **nós desenvolveremos o nosso próprio protocolo de comunicação na camada de aplicação**. Usaremos Sockets TCP puros (*raw sockets*) trafegando mensagens padronizadas em JSON. Isso garante a leveza de um malware real, mantendo a interoperabilidade e a abstração necessárias para o sistema distribuído funcionar.
