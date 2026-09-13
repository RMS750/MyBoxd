#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
DATA_DIR="$BACKEND/data"
RAW_DIR="$DATA_DIR/ml-32m-mirror"
ZIP_PATH="$DATA_DIR/ml-32m.zip"
OFFICIAL_URL="https://files.grouplens.org/datasets/movielens/ml-32m.zip"
MIRROR_BASE="https://huggingface.co/datasets/hazemessam/ml-32m/resolve/main"

mkdir -p "$DATA_DIR"

catalog_count() {
  "$BACKEND/.venv/bin/python" - <<'PY'
import sqlite3
from pathlib import Path
p = Path('myboxd.db')
if not p.exists():
    print(0)
else:
    c = sqlite3.connect(p)
    try:
        print(c.execute("SELECT COUNT(*) FROM movies WHERE catalog_source='movielens-32m'").fetchone()[0])
    except Exception:
        print(0)
    finally:
        c.close()
PY
}

verify_zip() {
  "$BACKEND/.venv/bin/python" - "$1" <<'PY'
import sys, zipfile
p = sys.argv[1]
with zipfile.ZipFile(p) as z:
    names = z.namelist()
    required = ('movies.csv', 'links.csv', 'ratings.csv', 'tags.csv')
    missing = [x for x in required if not any(n.endswith('/' + x) or n == x for n in names)]
    if missing:
        raise SystemExit(f"MovieLens archive is missing: {missing}")
    bad = z.testzip()
    if bad:
        raise SystemExit(f"MovieLens archive failed integrity check at: {bad}")
print("MovieLens archive verified.")
PY
}

checksum_file() {
  if command -v md5 >/dev/null 2>&1; then
    md5 -q "$1"
  elif command -v md5sum >/dev/null 2>&1; then
    md5sum "$1" | awk '{print $1}'
  else
    "$BACKEND/.venv/bin/python" - "$1" <<'PY'
import hashlib, sys
h = hashlib.md5()
with open(sys.argv[1], 'rb') as f:
    for chunk in iter(lambda: f.read(1024 * 1024), b''):
        h.update(chunk)
print(h.hexdigest())
PY
  fi
}

download_from_verified_mirror() {
  mkdir -p "$RAW_DIR"
  echo "Official GroupLens download is unavailable on this machine."
  echo "Using an HTTPS mirror and verifying every CSV against the published ML-32M checksums."
  echo

  for file in links.csv movies.csv ratings.csv tags.csv; do
    case "$file" in
      links.csv)   expected="8f033867bcb4e6be8792b21468b4fa6e" ;;
      movies.csv)  expected="0df90835c19151f9d819d0822e190797" ;;
      ratings.csv) expected="cf12b74f9ad4b94a011f079e26d4270a" ;;
      tags.csv)    expected="963bf4fa4de6b8901868fddd3eb54567" ;;
    esac
    dest="$RAW_DIR/$file"

    if [[ -f "$dest" ]] && [[ "$(checksum_file "$dest" 2>/dev/null || true)" == "$expected" ]]; then
      echo "✓ $file already downloaded and verified."
      continue
    fi

    echo "Downloading $file..."
    set +e
    curl --fail --location --retry 4 --retry-delay 2 --progress-bar -C - \
      "$MIRROR_BASE/$file?download=true" -o "$dest"
    status=$?
    set -e
    if [[ $status -ne 0 ]]; then
      echo "Resume failed; retrying $file from the beginning..."
      rm -f "$dest"
      curl --fail --location --retry 4 --retry-delay 2 --progress-bar \
        "$MIRROR_BASE/$file?download=true" -o "$dest"
    fi

    actual="$(checksum_file "$dest")"
    if [[ "$actual" != "$expected" ]]; then
      echo "Checksum verification FAILED for $file."
      echo "Expected: $expected"
      echo "Actual:   $actual"
      exit 1
    fi
    echo "✓ $file verified."
  done

  echo
  echo "All MovieLens files verified. Building local archive..."
  rm -f "$ZIP_PATH.part"
  "$BACKEND/.venv/bin/python" - "$RAW_DIR" "$ZIP_PATH.part" <<'PY'
from pathlib import Path
import sys, zipfile
raw = Path(sys.argv[1])
out = Path(sys.argv[2])
with zipfile.ZipFile(out, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
    for name in ('links.csv', 'movies.csv', 'ratings.csv', 'tags.csv'):
        z.write(raw / name, arcname=f'ml-32m/{name}')
print(f"Archive built: {out}")
PY
  mv "$ZIP_PATH.part" "$ZIP_PATH"
  rm -rf "$RAW_DIR"
}

cd "$BACKEND"
COUNT="$(catalog_count)"
if [[ "${COUNT:-0}" -ge 50000 ]]; then
  echo "MovieLens catalogue already installed (${COUNT} movies)."
  exit 0
fi

if [[ -f "$ZIP_PATH" ]]; then
  if verify_zip "$ZIP_PATH"; then
    echo "Using existing verified MovieLens archive."
  else
    echo "Existing MovieLens archive is invalid; downloading a fresh copy."
    rm -f "$ZIP_PATH"
  fi
fi

if [[ ! -f "$ZIP_PATH" ]]; then
  echo "Downloading MovieLens 32M (~228 MB) from GroupLens..."
  TMP="$ZIP_PATH.part"
  rm -f "$TMP"
  set +e
  curl --fail --location --retry 2 --retry-delay 2 --progress-bar "$OFFICIAL_URL" -o "$TMP"
  status=$?
  set -e

  if [[ $status -eq 0 ]]; then
    mv "$TMP" "$ZIP_PATH"
    if ! verify_zip "$ZIP_PATH"; then
      rm -f "$ZIP_PATH"
      download_from_verified_mirror
    fi
  else
    rm -f "$TMP"
    download_from_verified_mirror
  fi
fi

verify_zip "$ZIP_PATH"
echo "Importing the local ~87k-movie catalogue..."
"$BACKEND/.venv/bin/python" scripts/install_movielens_catalog.py --zip "$ZIP_PATH" --if-missing

COUNT="$(catalog_count)"
echo "Local MovieLens catalogue rows: $COUNT"
if [[ "${COUNT:-0}" -lt 50000 ]]; then
  echo "Catalogue import looks incomplete."
  exit 1
fi
