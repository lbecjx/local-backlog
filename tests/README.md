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

`test_update_status.py` is the dedicated suite for `update-status.sh` — the
only supported way to change a story's `Status`, reachable both from the
server's write endpoints and directly from the `/local-backlog:update-status`
slash command. It covers the canonical-value and bad-value refusals, the no-op
and backfill paths, `--expect` compare-and-swap, the `mkdir` lock (including
contention and the stale-lock timeout), file-mode preservation, the
per-transition `Note` and its `## History` line, the multi-line-`History`
regression, and the Step 3 start combo (`Status → In Progress` plus
`set-zone.sh … planner`, each half on its own). Its classes were moved here
from `test_idle_server.py` in LB-0016, where they had grown a second home
inside a file named after the server.

`test_update_status_scripts.py` covers the zone reader/writer (`get-zone.sh` /
`set-zone.sh`). `test_fix_scripts.py` covers the `fix` skill's repair scripts
(including the one `update-status.sh` invocation that belongs to a `fix`
flow). `test_story_model.py` ties the story model to the template and the
scripts. `test_open_backlog_script.py` covers `open-backlog.sh`'s resolution
reporting (`PROJECT:`/`ROOT:`) and its `--resolve-only` / `--root <path>`
shapes. `test_session_start_hook.py` and `test_opencode_plugin.py` cover the
SessionStart hook and its OpenCode delivery; `scripts/opencode-plugin.test.sh`
is that path's node harness.
