# local-backlog

For [Claude Code](https://code.claude.com) projects without access to a cloud-based issue tracker: create and manage stories as plain Markdown files, with auto-incrementing ticket codes and a searchable local viewer.

"Local" means no external service dependency — not necessarily private. Files can be gitignored or committed with the rest of the repo, by choice.

## Skills

| Skill | What it does |
|---|---|
| `/local-backlog:create-story` | Creates a story in `backlog/` with an auto-incrementing `<PREFIX>-XXXX` code, in structured ticket shape |
| `/local-backlog:open-backlog` | Serves the bundled viewer against `backlog/` and opens it in your browser |
| `/local-backlog:help` | Shows the backlog's current state and available skills |

## The viewer

A small pre-built React app, shipped ready to run — no `node`/`pnpm` needed to use it, only Python 3 to serve it locally (`python3 -m http.server` under the hood). It discovers stories live from `backlog/`: no manifest, no regeneration step. Edit a story and refresh the browser — the change is there.

Its source is a separate, independently versioned project: [`lbecjx/backlog-viewer`](https://github.com/lbecjx/backlog-viewer) (GPL-3.0-or-later, same author). This plugin only ships its pre-built output (`skills/open-backlog/dist/`); the app itself is never hand-edited from here.

## Installation

```
/plugin marketplace add /path/to/local-backlog
/plugin install local-backlog@local-backlog
```

(Replace the path with wherever you've cloned this repo, or its GitHub URL once published.)

## Recommended alongside this plugin

Once a story is created here, we suggest using [`workflow-dev`](https://github.com/lbecjx/workflow-dev) to actually work on it — `/workflow-dev:init backlog/<PREFIX>-XXXX-....md` works exactly like passing an external tracker's issue ID, and the rest of that plugin's flow (plan, implement, validate) picks up from there.

They're independent plugins, though — `local-backlog` has no awareness of `workflow-dev` and only creates/displays stories, with no opinion on how you implement them. Install either one on its own, or both; neither depends on the other.

## License

Licensed under the GNU General Public License v3.0 or later — see [LICENSE](./LICENSE) for the full text.

```
local-backlog — a local issue/story tracker for Claude Code, no cloud account needed
Copyright (C) 2026  Luis Becerra

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program. If not, see <https://www.gnu.org/licenses/>.
```

Author: Luis Becerra ([@lbecjx](https://github.com/lbecjx))
