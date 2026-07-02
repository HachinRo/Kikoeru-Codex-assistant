Use this project to operate the local ASMR stack.

Main web port:
- http://127.0.0.1:8890
- Dashboard: http://127.0.0.1:8890/asmr-library

Live stack:
- ASMR_STACK_ROOT: /Users/sainthenry/Documents/ASMR Pipeline/Web-UI
- ASMR_MEDIA_ROOT: /Volumes/TOSHIBA/AMSR
- NEOKIKOERU_DB: ~/Library/Application Support/neokikoeru/neokikoeru.db

Pipeline source/reference repo:
- refs/ASMR-Kikoeru -> https://github.com/HachinRo/Kikoeru-Codex-assistant

Important commands:
- rtk "<ASMR_STACK_ROOT>/bin/asmr-view" status
- rtk "<ASMR_STACK_ROOT>/bin/asmr-view" stop
- rtk "<ASMR_STACK_ROOT>/bin/asmr-view" --port 8890 start
- rtk "<ASMR_STACK_ROOT>/bin/asmr-library" dashboard
- rtk "<ASMR_STACK_ROOT>/bin/asmr-library" build
- rtk "<ASMR_STACK_ROOT>/bin/asmr-library" subs list-missing
- rtk "<ASMR_STACK_ROOT>/bin/asmr-library" subs fetch RJxxxx
