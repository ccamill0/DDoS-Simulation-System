# DDoS Simulation System

## 1. Definição do Projeto

O **Ambiente de Simulação de Ataques DDoS** é um laboratório controlado e conteinerizado, focado na aplicação prática de conceitos de **Segurança Ofensiva (Red Team)**, **Sistemas Distribuídos** e **Redes de Computadores**.

Um ataque de negação de serviço distribuída (DDoS) é semelhante a um  ataque de negação de serviço (DoS), mas é proveniente de várias fontes coordenadas. Por exemplo:

Seu objetivo principal é emular o comportamento de uma ***Botnet*** (uma rede de computadores zumbis controlada remotamente) executando ataques de **Negação de Serviço (DoS)**. O sistema demonstra na prática a orquestração de malwares simulados, a comunicação assíncrona entre o Comando e Controle (C2) e os nós, técnicas básicas de evasão (falsificação de cabeçalhos) e a diferença prática entre derrubar um serviço por **exaustão de volume** (UDP/HTTP Flood) versus **exaustão de estado/recursos** (Slowloris).

```markdown
ddos_sim_redteam/
│
├── c2.py               # Coordenador: controla bots, envia comandos e monitora a "saúde" do alvo (Telemetria)
├── bot.py              # Bot distribuído: conecta ao C2, forja User-Agents e executa HTTP/UDP/Slowloris
├── target.py           # Servidor alvo: API web genérica (vítima) focada apenas em tentar se manter no ar
│
├── requirements.txt    # Dependências mínimas do experimento
├── podman-compose.yml  # Orquestra C2, Target e múltiplos Bots simultaneamente
└── README.md           # Explicações, arquitetura ofensiva e instruções de execução
```

## 2. Processo Estrutural (O Ciclo de Vida do Sistema)

O funcionamento do projeto segue um fluxo cronológico focado na orquestração e medição do impacto do ataque.

**Fase 1: Inicialização e Orquestração (Infraestrutura)**

- O processo começa no terminal com o Podman. Ao executar o `podman-compose`, o sistema cria uma rede virtual isolada.
- Dentro dessa rede, nascem os contêineres: um atua como **Servidor Alvo**, um atua como **C2 (Coordenador)**, e múltiplos contêineres idênticos atuam como **Bots**. Todos recebem IPs virtuais fechados.

**Fase 2: Conexão e Prontidão (Botnet Armada)**

- Assim que os Bots "nascem", o script `bot.py` entra em ação. Eles abrem conexões TCP silenciosas direcionadas ao IP do C2.
- O C2 aceita essas conexões, armazena a lista de nós ativos e inicia uma *thread* de **Telemetria**: ele passa a "pingar" o Servidor Alvo a cada 2 segundos, mostrando no terminal o tempo de resposta (ex: *Alvo Saudável - Resposta em 20ms*).

**Fase 3: O Comando de Ataque (Orquestração C2)**

- O operador Red Team digita o comando no C2, definindo o alvo e a tática (ex: `ATTACK 192.168.1.10 SLOWLORIS`).
- O C2 empacota essa ordem em um JSON e faz um *broadcast* via Sockets para todos os Bots conectados simultaneamente.

**Fase 4: Execução e Evasão (Concorrência e Ataque)**

- Ao receberem o JSON, os Bots disparam múltiplas *threads* contra o Alvo.
- Dependendo do vetor escolhido, o comportamento muda: UDP inunda a rede, HTTP gera requisições massivas (sorteando *User-Agents* falsos para tentar enganar filtros simples) e o Slowloris abre milhares de conexões TCP lentas, prendendo os recursos da vítima.

**Fase 5: Medição de Impacto (Telemetria Ofensiva)**

- Enquanto o ataque ocorre, o operador observa o terminal do C2. A telemetria mostrará o tempo de resposta da vítima subindo drasticamente (de 20ms para 5000ms) até culminar em um *Timeout* ou *Connection Refused*, provando matematicamente que a Negação de Serviço foi bem-sucedida. Após o comando de `STOP`, o sistema mede quanto tempo o alvo leva para se recuperar.


<img width="1710" height="899" alt="Captura de Tela (950)" src="https://github.com/user-attachments/assets/8baefc11-e20c-4be4-bf36-b2a6af5ab00b" />

## 3. Roteiro de Estudos

Para dominar e defender a arquitetura deste projeto, o foco recai sobre infraestrutura, concorrência e táticas ofensivas de rede:

### 1. Redes de Computadores e Protocolos

- **Modelo TCP/IP:** Entenda a diferença entre a Camada 4 (Transporte) e a Camada 7 (Aplicação).
- **TCP vs. UDP:** A diferença entre protocolos orientados a conexão (*handshake*) e *connectionless* (dispara e esquece).
- **Protocolo HTTP e Cabeçalhos:** Como estruturar uma requisição GET nativa e o que é o cabeçalho `User-Agent`.
- **Sockets de Rede:** O uso de portas e IPs para comunicação de baixo nível (funções `bind`, `listen`, `accept`, `connect`).

### 2. Segurança Ofensiva e Vetores de Ataque (Red Team)

- **Ataques Volumétricos (UDP/HTTP Flood):** Como o foco é esgotar a banda da rede ou a capacidade de processamento imediato do alvo.
- **Exaustão de Recursos/Estado (Slowloris):** Estude como servidores web lidam com conexões simultâneas (limites de *threads* ou *workers*). Entenda como enviar requisições incompletas muito lentamente trava esses recursos.
- **Evasão Básica:** A teoria por trás da randomização de tráfego para contornar proteções simples baseadas em assinaturas.

### 3. Sistemas Distribuídos e Arquitetura

- **Master-Worker (Command & Control):** O padrão arquitetural onde o C2 emite ordens unificadas para a Botnet agir em sincronia.
- **Concorrência em Python:** A espinha dorsal do projeto. O C2 precisa ouvir você digitar, falar com os bots e medir a saúde do alvo *ao mesmo tempo*. Os bots precisam ouvir o C2 e atacar o alvo *ao mesmo tempo*. Estude `threading` e `asyncio`.
- **Serialização JSON:** Como empacotar comandos e enviá-los como bytes pela rede.

### 4. Orquestração com Podman (Infraestrutura Livre)

- **Contêineres OCI:** Entenda como empacotar scripts Python em contêineres usando `Containerfile` ou `Dockerfile`.
- **Daemonless e Rootless:** A diferença arquitetural do Podman (seguro e sem serviço central) em comparação ao Docker.
- **Redes Virtuais (Podman Compose):** Como desenhar um arquivo `.yaml` que levanta C2, Alvo e uma botnet escalável (`-scale bot=15`) em um ambiente seguro e isolado da internet real.

- Um invasor cria uma rede (botnet) de hosts infectados chamados zumbis, que são controlados por sistemas de tratamento.
- Os computadores zumbis examinam e infectam constantemente mais hosts, criando mais zumbis.
- Quando está pronto, o hacker instrui os sistemas controlador para fazer com que o botnet de zumbis execute um ataque de negação de serviço distribuído (DDoS).

## Questionário

1. **Dos modelos estudados algum se encaixa?(Em camadas, micro serviços, pu sub, P2P(estruturado/não-estruturado)**
2. **Arquitetura de SW interna**
3. **Como o sistema será testado?**
4. **Faz sentido usar algum tipo de middleware?**

aplicar tolerancia a falhas no controlador ou melhorar o sistema distribuido de bots (coordenação entre os bots)
