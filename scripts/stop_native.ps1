# stop_native.ps1
#
# Derruba e remove todos os containers e a rede criados por run_native.ps1.
#
# Uso:
#   .\scripts\stop_native.ps1

$names = @(
    "ddos-lab-target-1-1", "ddos-lab-target-2-1", "ddos-lab-target-3-1",
    "ddos-lab-lb-1",
    "ddos-lab-c2-a-1", "ddos-lab-c2-b-1", "ddos-lab-c2-c-1",
    "ddos-lab-bot-1-1", "ddos-lab-bot-2-1", "ddos-lab-bot-3-1", "ddos-lab-bot-4-1", "ddos-lab-bot-5-1",
    "ddos-lab-dashboard-1"
)

foreach ($n in $names) {
    Write-Host "==> Parando e removendo $n..." -ForegroundColor Cyan
    podman rm -f $n 2>$null | Out-Null
}

Write-Host "==> Removendo rede labnet..." -ForegroundColor Cyan
podman network rm labnet 2>$null | Out-Null

Write-Host "==> Concluído." -ForegroundColor Green
