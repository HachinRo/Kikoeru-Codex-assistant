#!/bin/sh
set -eu

"$HOME/.hermes/asmr/bin/asmr-view" status || true
lsof -nP -iTCP:8889 -iTCP:8890 -iTCP:8891 -sTCP:LISTEN || true
curl -fsS -I "http://127.0.0.1:8890/" | sed -n '1,8p'
curl -fsS -I "http://127.0.0.1:8890/asmr-library" | sed -n '1,8p'
