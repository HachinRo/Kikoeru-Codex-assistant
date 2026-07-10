Use this project to operate the local ASMR stack.

Main web port:
- http://127.0.0.1:8890
- Dashboard: http://127.0.0.1:8890/asmr-library
- Port 8890 intentionally binds to the trusted LAN; do not change that unless requested.

Live stack:
- ASMR_STACK_ROOT: /Users/sainthenry/Documents/ASMR Pipeline/Web-UI
- ASMR_MEDIA_ROOT: /Volumes/TOSHIBA/AMSR
- NEOKIKOERU_DB: ~/Library/Application Support/neokikoeru/neokikoeru.db

Pipeline source/reference repo:
- refs/ASMR-Kikoeru -> https://github.com/HachinRo/ASMR-Kikoeru

Important commands:
- "<ASMR_STACK_ROOT>/bin/asmr-view" status
- "<ASMR_STACK_ROOT>/bin/asmr-view" stop
- "<ASMR_STACK_ROOT>/bin/asmr-view" --port 8890 start
- "<ASMR_STACK_ROOT>/bin/asmr-library" dashboard
- "<ASMR_STACK_ROOT>/bin/asmr-library" build
- "<ASMR_STACK_ROOT>/bin/asmr-library" subs list-missing
- "<ASMR_STACK_ROOT>/bin/asmr-library" subs fetch RJxxxx
- "<ASMR_STACK_ROOT>/bin/media-stack-health"
- ./scripts/test.sh
- ./scripts/sync-skills.sh --check
