#!/bin/sh
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)"
ASMR_STACK_ROOT="${ASMR_STACK_ROOT:-$(CDPATH= cd -- "${SCRIPT_DIR}/../Web-UI" && pwd -P)}"

"${ASMR_STACK_ROOT}/bin/asmr-view" status || true
lsof -nP -iTCP:8890 -sTCP:LISTEN || true
curl -fsS -I "http://127.0.0.1:8890/" | sed -n '1,8p'
curl -fsS -I "http://127.0.0.1:8890/asmr-library" | sed -n '1,8p'
