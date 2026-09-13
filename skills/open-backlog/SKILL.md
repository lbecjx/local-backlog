---
name: open-backlog
description: Serves the bundled backlog viewer app against the project's backlog/ folder and opens it in the default browser. Use when the user says "open backlog", "show stories", or "view the backlog".
---

<!--
local-backlog — a local issue/story tracker for Claude Code, no cloud account needed
Copyright (C) 2026  lbecjx

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version. See LICENSE for the full text.
-->

# Open Local Backlog

Serves the plugin's bundled viewer (a small static React app, shipped pre-built
in `dist/`) with the project's own `backlog/` folder wired in live — no
generation step, no manifest, no rebuild. Edit a story's `.md` file and refresh
the browser; the new content is there. This requires a local HTTP server (the
viewer discovers stories via `fetch()`, which doesn't work over `file://`) —
that's the one meaningful difference from a plain static HTML file, and the
reason this skill needs `python3` on the machine.

## When to use

- The human wants to browse or search the backlog visually
- After creating or editing stories, to see them in the viewer
- To check the state of the backlog at a glance

## When NOT to use

- To create a story → use `/local-backlog:create-story`
- To start work on a story → use `/workflow-dev:init backlog/<PREFIX>-XXXX-....md` (prefix is whatever this project chose — see `backlog/.backlog-config.json`)

## Execution

Run this as **one shell script, in a single Bash call** — not one command per
step. Splitting it into several separate invocations makes the human approve
a permission prompt for each one; chained into one script, it's a single
approval for the whole flow. This is worth preserving deliberately: it's the
one thing most likely to regress if this skill is ever "cleaned up" into
separate steps again.

```bash
set -e

# Step 1: locate the backlog
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
if [ ! -d "$REPO_ROOT/backlog" ]; then
  echo "NO_BACKLOG"
  exit 0
fi

# Step 2: check for python3 (never fall back to python2, never auto-install)
if ! command -v python3 >/dev/null 2>&1; then
  echo "NO_PYTHON3"
  exit 0
fi

# Step 3: prepare the serving directory — a per-project staging dir outside
# the repo, so multiple projects never collide and the repo never gets a
# stray runtime folder. <skill-base-dir> is this skill's own directory.
HASH=$(printf '%s' "$REPO_ROOT" | shasum | cut -c1-12)   # sha1sum on Linux
STAGE="${TMPDIR:-/tmp}/local-backlog-viewer/$HASH"
mkdir -p "$STAGE"
cp -R "<skill-base-dir>/dist/." "$STAGE/"   # re-copy every run, keeps it in sync with the plugin
ln -sfn "$REPO_ROOT/backlog" "$STAGE/backlog"   # symlink, not a copy — edits show up on refresh

# Step 4: start the server, or reuse one already running for this project
if [ -f "$STAGE/.viewer.pid" ]; then
  PID=$(cut -d: -f1 "$STAGE/.viewer.pid")
  PORT=$(cut -d: -f2 "$STAGE/.viewer.pid")
  if ! kill -0 "$PID" 2>/dev/null; then
    PORT=""   # stale pid file, fall through to starting a new one
  fi
fi
if [ -z "$PORT" ]; then
  PORT=8420
  TRIES=0
  while lsof -i :"$PORT" >/dev/null 2>&1; do
    PORT=$((PORT + 1))
    TRIES=$((TRIES + 1))
    if [ "$TRIES" -ge 20 ]; then
      echo "NO_FREE_PORT"
      exit 0
    fi
  done
  nohup python3 -m http.server "$PORT" --directory "$STAGE" >/dev/null 2>&1 &
  echo "$!:$PORT" > "$STAGE/.viewer.pid"
fi

# Step 5: open it — default browser, never a hardcoded one, unless the human asked for one
open "http://localhost:$PORT/" 2>/dev/null || xdg-open "http://localhost:$PORT/" 2>/dev/null

echo "OPENED:$PORT"
echo "STORIES:$(ls "$REPO_ROOT"/backlog/*.md 2>/dev/null | wc -l | tr -d ' ')"
```

On Windows, `mklink /J` (directory junction, no admin rights needed) instead
of `ln -sfn`, and `start ""` instead of `open`/`xdg-open`. If junction
creation fails, fall back to `xcopy /E /I` and tell the human that copy won't
reflect future edits until the skill is re-run.

Read the script's own output to know what happened, then report to the human:

- **`NO_BACKLOG`** → there is no backlog yet; suggest `/local-backlog:create-story`. Do NOT create an empty folder just to open an empty viewer.
- **`NO_PYTHON3`** → "This viewer needs Python 3 to serve the app locally (it discovers stories live over HTTP, unlike a single static file). Install it from python.org or your system's package manager, then try again." Do not attempt to install anything yourself.
- **`NO_FREE_PORT`** → tell the human no port was free after 20 attempts, don't loop forever.
- **`OPENED:<port>` / `STORIES:<n>`** → tell the human how many stories are in `backlog/`, the URL that was opened, and that it's a live server — editing a story and refreshing the page is enough, no need to re-run this skill (only re-run it if the server needs restarting, e.g. after a reboot). Keep it to two or three lines — the browser window is the real output.

## What the viewer does

- **Left panel:** searchable list of story cards (code, title, type, status, AC progress, labels), with a colored accent border per status
- **Search:** matches code, title, and full body text
- **Status chips:** click to filter by status; click again to clear
- **Right panel:** the selected story rendered from its markdown, including syntax-highlighted code blocks

Story discovery happens client-side via the directory listing `python3 -m
http.server` generates for `$STAGE/backlog/` — there's no manifest file and
nothing to regenerate when stories change.

## Notes

- **The viewer app itself is never hand-edited from here.** It's a separate,
  independently versioned React project —
  [`lbecjx/backlog-viewer`](https://github.com/lbecjx/backlog-viewer) — GPL-3.0-or-later,
  same author. Changes to its UI happen there, get built, and the resulting
  `dist/` is what ships in this skill's own `dist/` folder.
- **The staging directory is disposable.** It's regenerated (app shell re-copied,
  backlog re-symlinked) on every invocation of this skill — nothing of value
  lives there that isn't also in `<repo-root>/backlog/` or the plugin's `dist/`.
- **One server per project, reused across invocations** — re-running this skill
  after already having it open just re-opens the same URL rather than spawning
  a second server on a new port.
- **Metadata comes from each story's table** (Code / Type / Priority / Status).
  A story with a malformed table still renders — the viewer falls back to
  sensible defaults rather than failing.
