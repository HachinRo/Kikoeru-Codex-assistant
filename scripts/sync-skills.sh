#!/bin/sh
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)"
PROJECT_ROOT="$(CDPATH= cd -- "${SCRIPT_DIR}/.." && pwd -P)"
CODEX_HOME="${CODEX_HOME:-${HOME}/.codex}"

usage() {
    echo "Usage: scripts/sync-skills.sh --check|--install" >&2
    exit 2
}

[ "$#" -eq 1 ] || usage
mode="$1"

for skill in asmr-library-ops asmr-subtitle-batch; do
    source_dir="${PROJECT_ROOT}/docs/skills/${skill}"
    target_dir="${CODEX_HOME}/skills/${skill}"
    [ -d "${source_dir}" ] || { echo "missing canonical skill: ${source_dir}" >&2; exit 1; }
    case "${mode}" in
        --check)
            [ -d "${target_dir}" ] || { echo "missing installed skill: ${target_dir}" >&2; exit 1; }
            diff -qr --exclude='__pycache__' "${source_dir}" "${target_dir}"
            ;;
        --install)
            mkdir -p "${target_dir}"
            rsync -a --delete --exclude='__pycache__/' "${source_dir}/" "${target_dir}/"
            echo "installed ${skill} -> ${target_dir}"
            ;;
        *) usage ;;
    esac
done
