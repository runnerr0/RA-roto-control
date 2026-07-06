#!/usr/bin/env bash
# Portable launcher for the RA Roto control console — tuned for older Macs.
# Finds a Python 3.6+, ensures pyserial is present, then runs the console.
# Usage:  ./run.sh [--port /dev/cu.usbmodemXXXX] [--cap N]
set -e
cd "$(dirname "$0")"

PY=""
for c in python3 python3.13 python3.12 python3.11 python3.10 python3.9 python3.8 python3.7 python3.6 python; do
  if command -v "$c" >/dev/null 2>&1; then
    if "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 6) else 1)' 2>/dev/null; then
      PY="$c"; break
    fi
  fi
done

if [ -z "$PY" ]; then
  echo "No Python 3.6+ found."
  echo "Install one from https://www.python.org/downloads/  (works on older macOS too),"
  echo "then re-run ./run.sh"
  exit 1
fi
echo "Using $("$PY" --version 2>&1)  ($(command -v "$PY"))"

if ! "$PY" -c 'import serial' >/dev/null 2>&1; then
  echo "pyserial not found — installing (user site)..."
  "$PY" -m pip install --user pyserial \
    || "$PY" -m pip install pyserial \
    || { echo "Could not install pyserial. Try:  $PY -m pip install --user pyserial"; exit 1; }
fi

echo "Starting console — open http://127.0.0.1:8791 in any modern browser."
exec "$PY" roto_bench.py "$@"
