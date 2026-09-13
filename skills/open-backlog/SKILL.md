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

Run the bundled script with a single, fixed command:

```bash
bash "<skill-base-dir>/scripts/open-backlog.sh"
```

Always invoke it exactly like that — same literal command line every time,
nothing inlined or interpolated into it. That's deliberate: a fixed command
string is what lets Claude Code's permission system recognize "this is the
same command as before" across runs, instead of re-prompting on every
invocation the way an inline script (whose text is rebuilt fresh each time)
would. Do not paste the script's contents inline instead of calling the file
— that's the one thing most likely to regress this if the skill is ever
"cleaned up" later.

The script does all of it in order: finds the repo root and its `backlog/`
folder, checks for `python3`, stages the pre-built viewer into a per-project
temp directory with the real `backlog/` symlinked in live, starts (or reuses)
the local server, and opens it in the default browser. On Windows, it uses a
directory junction (`mklink /J`, no admin rights needed) instead of a symlink,
and falls back to `xcopy /E /I` if that fails — that copy won't reflect future
edits until the skill is re-run, which is worth telling the human if it happens.

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
