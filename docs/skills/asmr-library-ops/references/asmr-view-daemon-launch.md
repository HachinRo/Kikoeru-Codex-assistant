---
name: asmr-view-daemon-launch
description: os.fork() + os.setsid() in asmr-view's cmd_start silently kills the server on macOS. Use subprocess.Popen(start_new_session=True) with a hidden subcommand instead.
version: 1.0.0
platforms: [macos]
metadata:
  hermes:
    tags: [daemon, fork, macos, python, asmr-view, subprocess]
    category: media
---

# asmr-view daemon-launch: subprocess.Popen beats os.fork on macOS

`asmr-library view start` shells out to `<ASMR_STACK_ROOT>/bin/asmr-view
start`, which used to do `os.fork() + os.setsid() + serve_forever()`.
The forked grandchild **silently died** on macOS the moment the
launching shell exited — no error, no traceback, just a "serving
on" line in the log and then the process is gone. The user
observed: "started (pid N) but health check failed" and the server
wasn't actually accepting connections.

## Why os.fork() fails here

`os.fork()` creates a child that inherits the parent's file
descriptors, controlling terminal, and process group. `os.setsid()`
should detach it into a new session. On macOS in a
Hermes-controlled terminal session, something about the session
lineage (`launchd` → shell → python → forked child) still treats
the forked child as a job-control descendant. When the shell exits,
the child gets SIGHUP/SIGTERM via that relationship even with
`setsid()`.

The symptom: `serve_forever()` starts, the print "serving on" fires
to the log, then the process vanishes. No exception, no Python
traceback. Health check from the parent times out.

## The fix: subprocess.Popen with start_new_session=True

Replace the fork+setsid code with a re-exec into the same script
using a new top-level process:

```python
# In cmd_start (the parent):
import subprocess
proc = subprocess.Popen(
    [sys.executable, __file__, "--host", host, "--port", str(port), "_serve_foreground"],
    stdin=subprocess.DEVNULL,
    stdout=log_fp,
    stderr=log_fp,
    start_new_session=True,  # this is the key — new session, new pgrp
    close_fds=True,
)
log_fp.close()
# then do the health check loop, return
```

The child process is a brand new top-level Python process — not a
fork of the shell, not a fork of the parent's interpreter. macOS
launchd tracks it as a fresh process and does not cascade SIGHUP
when the launching shell exits.

Add a hidden subcommand `_serve_foreground` to argparse that just
runs `serve_forever` in the current process. Mark it with
`help=argparse.SUPPRESS` so it doesn't show in --help.

## Detection

If you see this pattern in the log:
```
asmr-view serving on http://0.0.0.0:8890
[then nothing — no request log lines, no traceback]
```
and `lsof -nP -iTCP:8890 -sTCP:LISTEN` returns nothing, the fork
died silently. Switch to the subprocess.Popen pattern.

## Why double-fork doesn't help

I tried `os.fork() → setsid() → fork() → grandchild serves` (the
classic Unix double-fork pattern). Same result: grandchild dies.
The issue is that the **second** fork still creates a child of the
first child, and macOS still tracks the lineage. The fix is to
**re-exec** so the process is a completely new entry point.

## Related

- `<ASMR_STACK_ROOT>/bin/asmr-view` `cmd_start` (parent) and
  `cmd_serve_foreground` (child) — current implementation.
- `docs/skills/asmr-library-ops/SKILL.md` — asmr-library
  skill, includes the `asmr-view start` workflow.
