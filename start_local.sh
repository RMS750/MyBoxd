#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if [[ ! -f .env ]] || ! grep -Eq '^TMDB_API_KEY=.+$' .env; then
  echo "TMDB_API_KEY is missing."
  echo "Run: open -e \"$ROOT/.env\""
  echo "Paste the key after TMDB_API_KEY=, save, then run this script again."
  exit 1
fi
if [[ ! -x backend/.venv/bin/uvicorn ]] || [[ ! -d frontend/node_modules ]]; then
  echo "Dependencies are not installed. Run: bash setup_local.sh"
  exit 1
fi

# Stop only stale MyBoxd uvicorn/vite processes on the two local ports. This
# prevents Vite from silently moving to 5174 while an older frontend stays on 5173.
bash "$ROOT/stop_local.sh"
sleep 0.5

cleanup(){
  kill "${BACK_PID:-}" "${FRONT_PID:-}" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

(
  cd "$ROOT/backend"
  source .venv/bin/activate
  exec uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
) &
BACK_PID=$!

(
  cd "$ROOT/frontend"
  exec npm run dev -- --host 127.0.0.1 --strictPort
) &
FRONT_PID=$!

echo
echo "MyBoxd is starting..."
echo "Website: http://localhost:5173"
echo "API:     http://localhost:8000"
echo

api_ready=0
front_ready=0
i=0
while [[ "$i" -lt 30 ]]; do
  if curl -fsS "http://localhost:8000/api/health" >/dev/null 2>&1; then api_ready=1; fi
  if curl -fsS "http://localhost:5173/" >/dev/null 2>&1; then front_ready=1; fi
  if [[ "$api_ready" -eq 1 && "$front_ready" -eq 1 ]]; then break; fi
  if ! kill -0 "$BACK_PID" 2>/dev/null || ! kill -0 "$FRONT_PID" 2>/dev/null; then break; fi
  i=$((i + 1))
  sleep 1
done

if [[ "$api_ready" -ne 1 || "$front_ready" -ne 1 ]]; then
  echo "MyBoxd did not finish starting. Check the error messages above."
  exit 1
fi

echo "MyBoxd is ready."
echo "Press Control+C to stop it."
if command -v open >/dev/null 2>&1; then
  open "http://localhost:5173" >/dev/null 2>&1 || true
fi

# macOS ships Bash 3.2, which does not support `wait -n`. Keep the launcher
# alive with a portable loop and stop both processes if either one exits.
while kill -0 "$BACK_PID" 2>/dev/null && kill -0 "$FRONT_PID" 2>/dev/null; do
  sleep 1
done

echo "A MyBoxd process stopped. See the messages above for the cause."
exit 1
