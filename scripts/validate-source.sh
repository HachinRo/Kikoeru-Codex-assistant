#!/bin/sh
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)"
ROOT="$(CDPATH= cd -- "${SCRIPT_DIR}/.." && pwd -P)"
cd "${ROOT}"

for forbidden in \
    'Web-UI/serve-config.json' \
    'Web-UI/.asmr-one-cookies.txt' \
    'Web-UI/.asmroner-data' \
    'Web-UI/bin/asmroner' \
    'Web-UI/bin/neokikoeru' \
    'Web-UI/serve-index' \
    'Web-UI/listen-index' \
    'Web-UI/backups'; do
    if git ls-files -- "${forbidden}" "${forbidden}/**" | grep -q .; then
        echo "forbidden tracked path: ${forbidden}" >&2
        exit 1
    fi
done

test -f .gitmodules
git config -f .gitmodules --get submodule.refs/ASMR-Kikoeru.url | grep -Fx 'https://github.com/HachinRo/ASMR-Kikoeru.git' >/dev/null
test -f Web-UI/kikoeru-spa/js/app.051b603f.fix11.js
grep -F 'app.051b603f.fix11.js' Web-UI/kikoeru-spa/index.html >/dev/null
if rg -n '\brtk\b' docs/skills; then
    echo "obsolete rtk reference in canonical skills" >&2
    exit 1
fi
echo "sanitized source validation OK"
