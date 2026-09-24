# Tests

Dev-only — never required to install or use this plugin. These exercise the
real `idle_server.py` process over real HTTP (a scratch `local-backlog/`
project per test, staged the same way `open-backlog.sh` actually does), not
a mocked handler standing in for it.

## Running

```bash
python3 -m venv .venv
source .venv/bin/activate       # .venv\Scripts\activate on Windows
pip install -r requirements-dev.txt
pytest
```

No `uv`, no lockfile, no project-wide package manager — the plugin itself
has no build step and no external dependencies (no `jq`, no npm/pip package
of its own), and `pytest` is the one deliberate exception for its dev-only
tests, kept to the smallest possible footprint: one package, installed with
the `pip`/`venv` that already ship with the `python3` this plugin already
requires.

## What's covered

`test_idle_server.py` formalizes the manual QA pass run against Task Group 1
(local-backlog's write endpoints — `/api/status`, `/api/board`, the archive
transaction and its rollback, the concurrency fix, and input validation).
`update-status.sh`'s own `mkdir` lock gets one direct test outside the
server (`TestUpdateStatusLock`), since it's also invoked from outside the
HTTP path (the `/local-backlog:update-status` slash command).
