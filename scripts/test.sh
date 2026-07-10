#!/bin/sh
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)"
ROOT="$(CDPATH= cd -- "${SCRIPT_DIR}/.." && pwd -P)"
cd "${ROOT}"

for script in Web-UI/bin/asmr-library Web-UI/bin/asmr-library-worker Web-UI/bin/media-stack-health Web-UI/bin/neokikoeru-fetch Web-UI/bin/neokikoeru-serve scripts/*.sh; do
    sh -n "${script}"
done
python3 -m unittest discover -s tests -v
scripts/validate-source.sh
