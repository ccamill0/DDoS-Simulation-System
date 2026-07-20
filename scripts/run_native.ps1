# run_native.ps1
#
# Alternativa ao `podman-compose up`, usando `podman run` sequencial em vez
# de builds/starts em paralelo. Existe porque `podman-compose` abre uma
# conexão SSH por serviço simultaneamente contra a Podman Machine (WSL2), e
# sob rajada isso pode falhar com "ssh: handshake failed: EOF" mesmo com a
# máquina saudável. Rodando um `podman run` de cada vez, isso não acontece.
#
# Pré-requisito: as imagens já precisam existir (rode
# `podman-compose -f podman-compose.yml build` pelo menos uma vez, ou aceite
# que este script vai falhar em `podman run` se a imagem não existir --
# nesse caso, builde manualmente com `podman build -t <nome> .\<pasta>`).
#
# Uso:
#   .\scripts\run_native.ps1
#
# Para derrubar tudo depois: .\scripts\stop_native.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "==> Criando rede labnet (10.20.0.0/24, isolada)..." -ForegroundColor Cyan
podman network create --driver bridge --internal --subnet 10.20.0.0/24 labnet 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "    (rede já existe, seguindo em frente)" -ForegroundColor DarkGray
}

function Start-Container {
    param($Name, $Image, $Ip, [string[]]$EnvVars, [string[]]$ExtraArgs)

    Write-Host "==> Subindo $Name ($Ip)..." -ForegroundColor Cyan
    $envArgs = @()
    foreach ($e in $EnvVars) { $envArgs += @("-e", $e) }

    $args = @(
        "run", "-d", "--name", $Name,
        "--network", "labnet", "--ip", $Ip,
        "--restart", "on-failure"
    ) + $envArgs + $ExtraArgs + @($Image)

    & podman @args
    if ($LASTEXITCODE -ne 0) {
        Write-Host "    FALHOU ao subir $Name — veja o erro acima." -ForegroundColor Red
    }
    Start-Sleep -Milliseconds 400   # pequena pausa entre containers, de propósito
}

# ---------------------------------------------------------- defensivo --
Start-Container -Name "ddos-lab-target-1-1" -Image "localhost/ddos-lab_target-1:latest" `
    -Ip "10.20.0.11" -EnvVars @("REPLICA_ID=target-1", "PEERS=10.20.0.12:8000,10.20.0.13:8000")

Start-Container -Name "ddos-lab-target-2-1" -Image "localhost/ddos-lab_target-2:latest" `
    -Ip "10.20.0.12" -EnvVars @("REPLICA_ID=target-2", "PEERS=10.20.0.11:8000,10.20.0.13:8000")

Start-Container -Name "ddos-lab-target-3-1" -Image "localhost/ddos-lab_target-3:latest" `
    -Ip "10.20.0.13" -EnvVars @("REPLICA_ID=target-3", "PEERS=10.20.0.11:8000,10.20.0.12:8000")

Write-Host "==> Subindo ddos-lab-lb-1 (10.20.0.10)..." -ForegroundColor Cyan
podman run -d --name ddos-lab-lb-1 `
    --network labnet --ip 10.20.0.10 `
    -v "${root}\lb\haproxy.cfg:/usr/local/etc/haproxy/haproxy.cfg:ro" `
    -p 8080:8080 -p 8404:8404 `
    docker.io/library/haproxy:2.9
Start-Sleep -Milliseconds 400

# ---------------------------------------------------------- ofensivo --
Start-Container -Name "ddos-lab-c2-a-1" -Image "localhost/ddos-lab_c2-a:latest" -Ip "10.20.0.21" -EnvVars @(
    "NODE_ID=1",
    "PEERS=2:10.20.0.22,3:10.20.0.23",
    "BOTS=10.20.0.31:7000,10.20.0.32:7000,10.20.0.33:7000,10.20.0.34:7000,10.20.0.35:7000",
    "LB_HEALTH_URL=http://10.20.0.10:8080/health"
)

Start-Container -Name "ddos-lab-c2-b-1" -Image "localhost/ddos-lab_c2-b:latest" -Ip "10.20.0.22" -EnvVars @(
    "NODE_ID=2",
    "PEERS=1:10.20.0.21,3:10.20.0.23",
    "BOTS=10.20.0.31:7000,10.20.0.32:7000,10.20.0.33:7000,10.20.0.34:7000,10.20.0.35:7000",
    "LB_HEALTH_URL=http://10.20.0.10:8080/health"
)

Start-Container -Name "ddos-lab-c2-c-1" -Image "localhost/ddos-lab_c2-c:latest" -Ip "10.20.0.23" -EnvVars @(
    "NODE_ID=3",
    "PEERS=1:10.20.0.21,2:10.20.0.22",
    "BOTS=10.20.0.31:7000,10.20.0.32:7000,10.20.0.33:7000,10.20.0.34:7000,10.20.0.35:7000",
    "LB_HEALTH_URL=http://10.20.0.10:8080/health"
)

Start-Container -Name "ddos-lab-bot-1-1" -Image "localhost/ddos-lab_bot-1:latest" `
    -Ip "10.20.0.31" -EnvVars @("MY_ID=bot-1", "NEIGHBORS=10.20.0.32:7000,10.20.0.33:7000")

Start-Container -Name "ddos-lab-bot-2-1" -Image "localhost/ddos-lab_bot-2:latest" `
    -Ip "10.20.0.32" -EnvVars @("MY_ID=bot-2", "NEIGHBORS=10.20.0.31:7000,10.20.0.33:7000,10.20.0.34:7000")

Start-Container -Name "ddos-lab-bot-3-1" -Image "localhost/ddos-lab_bot-3:latest" `
    -Ip "10.20.0.33" -EnvVars @("MY_ID=bot-3", "NEIGHBORS=10.20.0.31:7000,10.20.0.32:7000,10.20.0.34:7000,10.20.0.35:7000")

Start-Container -Name "ddos-lab-bot-4-1" -Image "localhost/ddos-lab_bot-4:latest" `
    -Ip "10.20.0.34" -EnvVars @("MY_ID=bot-4", "NEIGHBORS=10.20.0.32:7000,10.20.0.33:7000,10.20.0.35:7000")

Start-Container -Name "ddos-lab-bot-5-1" -Image "localhost/ddos-lab_bot-5:latest" `
    -Ip "10.20.0.35" -EnvVars @("MY_ID=bot-5", "NEIGHBORS=10.20.0.33:7000,10.20.0.34:7000")

# ------------------------------------------------------ observabilidade --
Write-Host "==> Subindo ddos-lab-dashboard-1 (10.20.0.40)..." -ForegroundColor Cyan
podman run -d --name ddos-lab-dashboard-1 `
    --network labnet --ip 10.20.0.40 `
    -e "TARGETS=target-1:10.20.0.11:8000,target-2:10.20.0.12:8000,target-3:10.20.0.13:8000" `
    -e "C2_NODES=1:10.20.0.21,2:10.20.0.22,3:10.20.0.23" `
    -e "LB_STATS_URL=http://10.20.0.10:8404/stats;csv" `
    -e "POLL_INTERVAL=1.0" `
    -p 8090:8090 `
    --restart on-failure `
    localhost/ddos-lab_dashboard:latest

Write-Host ""
Write-Host "==> Pronto. Confira com: podman ps -a" -ForegroundColor Green
Write-Host "==> Dashboard: http://localhost:8090" -ForegroundColor Green
