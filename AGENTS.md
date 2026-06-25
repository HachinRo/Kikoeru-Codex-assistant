Use this project to operate the local ASMR stack.

Main web port:
- http://127.0.0.1:8890
- Dashboard: http://127.0.0.1:8890/asmr-library

Live stack:
- ~/.hermes/asmr
- /Volumes/TOSHIBA/AMSR
- ~/Library/Application Support/neokikoeru/neokikoeru.db

Important commands:
- rtk "$HOME/.hermes/asmr/bin/asmr-view" status
- rtk "$HOME/.hermes/asmr/bin/asmr-view" stop
- rtk "$HOME/.hermes/asmr/bin/asmr-view" --port 8890 start
- rtk "$HOME/.hermes/asmr/bin/asmr-library" dashboard
- rtk "$HOME/.hermes/asmr/bin/asmr-library" build
- rtk "$HOME/.hermes/asmr/bin/asmr-library" subs list-missing
- rtk "$HOME/.hermes/asmr/bin/asmr-library" subs fetch RJxxxx
