#!/usr/bin/env bash
set -euo pipefail

for cmd in python3 npm curl; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Missing required command: $cmd"
    exit 1
  fi
done

bash "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/setup_local.sh"
