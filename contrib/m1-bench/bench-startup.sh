#!/bin/bash
#
# Замер старта и памяти qBittorrent.
#   ./bench-startup.sh /Applications/qbittorrent.app 3
#
# Считает время от exec до строки "запущен"/"started" в логе профиля,
# затем RSS после 15 секунд простоя. Профиль каждый раз свежий,
# чтобы не мешали кэш и старые настройки.
#
set -uo pipefail

APP="${1:?путь к .app}"
RUNS="${2:-3}"
BIN="$APP/Contents/MacOS/qbittorrent"
NAME="$(basename "$APP" .app)"

[ -x "$BIN" ] || { echo "нет бинарника: $BIN" >&2; exit 1; }

results=()
rss_list=()

for run in $(seq 1 "$RUNS"); do
  PROF="$(mktemp -d /tmp/qbtbench.XXXXXX)"
  LOG="$PROF/qBittorrent/data/logs/qbittorrent.log"

  start=$(python3 -c 'import time; print(time.time())')
  "$BIN" --profile="$PROF" >/dev/null 2>&1 &
  pid=$!

  ready=""
  for _ in $(seq 1 300); do   # до 30 с
    if [ -f "$LOG" ] && grep -qE 'запущен|started' "$LOG" 2>/dev/null; then
      ready=$(python3 -c "import time; print(f'{time.time()-$start:.3f}')")
      break
    fi
    sleep 0.1
  done

  sleep 15
  rss=$(ps -o rss= -p "$pid" 2>/dev/null | tr -d ' ')
  cpu=$(ps -o %cpu= -p "$pid" 2>/dev/null | tr -d ' ')
  kill "$pid" 2>/dev/null
  wait "$pid" 2>/dev/null
  rm -rf "$PROF"

  if [ -n "$ready" ]; then
    results+=("$ready")
    rss_list+=("$rss")
    printf 'прогон %d: старт %s с, RSS %s МБ, CPU %s%%\n' "$run" "$ready" "${rss/$((1024))/}" "$cpu"
    printf '          (RSS %s КБ)\n' "$rss"
  else
    echo "прогон $run: приложение не стартовало за 30 с" >&2
  fi
done

if [ ${#results[@]} -gt 0 ]; then
  python3 - "$NAME" "${results[@]}" -- "${rss_list[@]}" <<'PY'
import statistics, sys
name = sys.argv[1]
sep = sys.argv.index('--')
spec = [float(x) for x in sys.argv[2:sep]]
rss = [int(x) / 1024 for x in sys.argv[sep + 1:]]
print()
print(f"{name}: старт median {statistics.median(spec):.2f} с "
      f"(min {min(spec):.2f}, max {max(spec):.2f}), "
      f"RSS median {statistics.median(rss):.1f} МБ")
PY
fi
