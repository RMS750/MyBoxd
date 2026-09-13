#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

echo "=== MyBoxd local setup ==="

if [[ ! -f .env ]]; then
  cp .env.example .env
fi

# Force safe local defaults while preserving any existing TMDB key.
python3 - <<'PY'
from pathlib import Path
p=Path('.env')
lines=p.read_text().splitlines()
updates={
  'ENVIRONMENT':'development',
  'DATABASE_URL':'sqlite:///./myboxd.db',
  'FRONTEND_URL':'http://localhost:5173',
  'TMDB_ENRICH_LIMIT':'120',
  'CANDIDATE_ENRICH_LIMIT':'96',
  'AUTO_CREATE_SCHEMA':'true',
}
seen=set(); out=[]
for line in lines:
    if '=' in line and not line.lstrip().startswith('#'):
        key=line.split('=',1)[0].strip()
        if key in updates:
            out.append(f'{key}={updates[key]}'); seen.add(key); continue
    out.append(line)
for key,value in updates.items():
    if key not in seen: out.append(f'{key}={value}')
p.write_text('\n'.join(out)+'\n')
PY

printf 'VITE_API_URL=\n' > frontend/.env.local

echo "[1/3] Setting up backend..."
cd "$ROOT/backend"
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
alembic upgrade head
TMDB_API_KEY="" pytest -q
python -m compileall -q app
ruff check app tests

echo
echo "[2/3] Installing fast local movie catalogue..."
bash "$ROOT/scripts/install_movie_catalog.sh"

echo
echo "[3/3] Setting up frontend..."
cd "$ROOT/frontend"
npm install
npm run typecheck
npm run build

echo
echo "Setup complete."
if grep -Eq '^TMDB_API_KEY=.+$' "$ROOT/.env"; then
  echo "Run: bash start_local.sh"
  echo "Then open: http://localhost:5173"
else
  echo "Before starting, add your TMDB key:"
  echo "  open -e "$ROOT/.env""
  echo "Paste it after TMDB_API_KEY= and save."
  echo "Then run: bash start_local.sh"
fi
