---
name: help
description: Shows the local backlog's current state and available skills. Use when the user says "help", "what skills are there", or needs guidance on this plugin.
---

<!--
local-backlog — a local issue/story tracker for Claude Code, no cloud account needed
Copyright (C) 2026  Luis Becjx

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version. See LICENSE for the full text.
-->

# Help

Detects whether this project has a local backlog yet and suggests the next step.

## Execution

### Step 1: Detect project state

Check for `backlog/` at the repo root (`git rev-parse --show-toplevel`, fall back to cwd):

1. **`backlog/` doesn't exist** → "No local backlog yet in this project. Run `/local-backlog:create-story` to create the first one."
2. **`backlog/` exists with stories** → count the `<PREFIX>-*.md` files and list a few codes: "N stories in the local backlog (e.g. NB-0001, NB-0003). `/local-backlog:open-backlog` to browse them, or `/local-backlog:create-story` to add another."
3. **`backlog/` exists but is empty** (config file only, no stories yet — unusual but possible if creation was interrupted) → "Backlog folder exists but has no stories yet. `/local-backlog:create-story` to create the first one."

### Step 2: Show status and available skills

```
Local Backlog — Status

Backlog: backlog/ (N stories)

Available skills:
  /local-backlog:create-story — Create a story with an auto-incrementing code
  /local-backlog:open-backlog — Serve the viewer and open it in the browser
  /local-backlog:help         — This screen
```

## Relationship to workflow-dev

This plugin only creates and displays stories — it has no opinion on how you implement them. Once you're ready to work on one:

```
/workflow-dev:init backlog/<PREFIX>-XXXX-....md
```

works exactly like passing an external tracker's issue ID — the `.md` file *is* the story.
`workflow-dev` is a separate, independent plugin; this one has no dependency on it.

## When to use each skill

| Situation | Skill |
|-----------|-------|
| Capturing a new story (with or without an external tracker) | `/local-backlog:create-story` |
| Browsing or searching the backlog visually | `/local-backlog:open-backlog` |
| Not sure what's next | `/local-backlog:help` |

## When NOT to use this plugin

- The project already uses a cloud-based issue tracker and that's where stories should live
- You need to implement a story, not just capture or browse it → that's `workflow-dev`
