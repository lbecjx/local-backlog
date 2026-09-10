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

### Step 1: Locate the backlog

1. Repo root: `git rev-parse --show-toplevel` (fall back to cwd if not a git repo)
2. Look for `backlog/` at the root
3. **If it does not exist** → tell the human there is no backlog yet and suggest
   `/local-backlog:create-story` to create the first story. Do NOT create an
   empty folder just to open an empty viewer, and do NOT proceed to the steps below.

### Step 2: Check for python3

```bash
command -v python3
```

**Not found** → stop and tell the human: "This viewer needs Python 3 to serve
the app locally (it isn't a single static file like the old generator — it
discovers stories live over HTTP). Install it from python.org or your system's
package manager, then try again." Do not fall back to `python` (Python 2) or
attempt to install anything yourself.

### Step 3: Prepare the serving directory

The viewer is a pre-built static app at `<skill-base-dir>/dist/` (React + Vite,
already built — no `pnpm`/`node` needed to run it). It gets served from a
per-project staging directory outside the repo, not from inside the plugin
install or the repo itself, so multiple projects using this skill never
collide and the repo never gets a stray runtime folder.

1. Compute a stable staging directory from the repo root path, e.g.:
   ```bash
   HASH=$(printf '%s' "<repo-root>" | shasum | cut -c1-12)   # or sha1sum on Linux
   STAGE="${TMPDIR:-/tmp}/local-backlog-viewer/$HASH"
   ```
2. `mkdir -p "$STAGE"`, then copy the app shell in fresh every run (cheap — a
   few hundred KB): `cp -R "<skill-base-dir>/dist/." "$STAGE/"`. Always
   re-copy, even if `$STAGE` already existed — keeps the served app in sync if
   the plugin itself was updated since the last run.
3. Wire in the real backlog, live:
   - **macOS/Linux:** `ln -sfn "<repo-root>/backlog" "$STAGE/backlog"` (symlink,
     not a copy — story edits are picked up on the next browser refresh with
     zero extra steps, matching the no-regeneration design of the viewer itself)
   - **Windows:** `mklink /J "%STAGE%\backlog" "<repo-root>\backlog"` (directory
     junction — doesn't require admin rights, unlike a symlink). If junction
     creation fails for some reason, fall back to `xcopy /E /I` and tell the
     human this copy won't reflect future edits until the skill is re-run.

### Step 4: Start (or reuse) the server

A symlinked backlog means a previously-started server for this project is
already live — there's no need to restart it just because a story changed.

1. Check `$STAGE/.viewer.pid` for a previous run: does it contain a PID that's
   still alive, and did that process bind the recorded port? If yes, skip
   straight to Step 5 with that port — nothing else to do.
2. Otherwise, pick a port: start at `8420`, increment until one isn't already
   bound (`lsof -i :$PORT` or equivalent). Cap the search (e.g. 20 attempts) —
   if nothing free turns up, tell the human instead of looping forever.
3. Start the server detached from this session so it outlives the skill
   invocation: `python3 -m http.server "$PORT" --directory "$STAGE" >/dev/null 2>&1 &`
   then `disown` it (or the platform equivalent) so it isn't tied to this shell.
4. Write `$STAGE/.viewer.pid` with the PID and port (e.g. `<pid>:<port>`), so
   the next invocation can find and reuse it per Step 4.1.

### Step 5: Open it

| Platform | Command |
|---|---|
| macOS | `open "http://localhost:$PORT/"` |
| Linux | `xdg-open "http://localhost:$PORT/"` |
| Windows | `start "" "http://localhost:%PORT%/"` |

Use the default browser (`open`), not a hardcoded browser name.

If the human explicitly asks for a specific browser, target it:
`open -a "Google Chrome" "http://localhost:$PORT/"` on macOS.

### Step 6: Confirm

Tell the human:
- How many stories are in `backlog/` (a quick count of `<PREFIX>-*.md` is enough — the viewer itself will show the exact number once loaded)
- The URL that was opened
- That it's a live server: editing a story and refreshing the page is enough, no need to re-run this skill — only re-run it if the server ever needs restarting (e.g. after a machine reboot)

Keep it to two or three lines — the browser window is the real output.

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
