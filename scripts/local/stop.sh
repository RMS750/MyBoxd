#!/usr/bin/env bash
set -euo pipefail

stop_port_if_myboxd(){
  local port="$1"
  command -v lsof >/dev/null 2>&1 || return 0
  local pids
  pids="$(lsof -ti tcp:"$port" 2>/dev/null || true)"
  [[ -z "$pids" ]] && return 0
  for pid in $pids; do
    local cmd
    cmd="$(ps -p "$pid" -o command= 2>/dev/null || true)"
    if [[ "$cmd" == *uvicorn*app.main:app* || "$cmd" == *node_modules/.bin/vite* ]]; then
      kill "$pid" 2>/dev/null || true
    fi
  done
}

stop_port_if_myboxd 8000
stop_port_if_myboxd 5173
