#!/usr/bin/env bash
# chaos.sh — utilitários de caos para o plano de testes (§14 da especificação)
#
# Uso:
#   ./scripts/chaos.sh kill-target 1        # derruba target-1 (crash)
#   ./scripts/chaos.sh kill-target 1 2      # derruba target-1 e target-2
#   ./scripts/chaos.sh kill-leader-c2       # derruba o nó C2 atualmente líder
#   ./scripts/chaos.sh watch-lb             # observa o pool do HAProxy (stats)
set -euo pipefail

CMD="${1:-}"
shift || true

case "$CMD" in
  kill-target)
    for n in "$@"; do
      echo "Derrubando target-$n ..."
      podman stop "ddos-lab_target-${n}_1" 2>/dev/null || podman stop "target-${n}"
    done
    ;;
  kill-leader-c2)
    echo "Verifique os logs (podman logs c2-a / c2-b / c2-c) para achar o líder atual"
    echo "e então rode: podman stop <container_do_lider>"
    ;;
  watch-lb)
    echo "Abra http://localhost:8404/stats (ou 'podman exec -it lb sh' se a rede"
    echo "estiver isolada) para ver ejection/readmissão de réplicas em tempo real."
    ;;
  *)
    echo "Uso: $0 {kill-target N [N...]|kill-leader-c2|watch-lb}"
    exit 1
    ;;
esac
