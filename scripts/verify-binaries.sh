#!/bin/sh
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)"
STACK_ROOT="${ASMR_STACK_ROOT:-$(CDPATH= cd -- "${SCRIPT_DIR}/../Web-UI" && pwd -P)}"

cd "${STACK_ROOT}"
shasum -a 256 -c bin/checksums.sha256
