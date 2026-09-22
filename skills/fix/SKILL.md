---
name: fix
description: Diagnoses and fixes problems with the local backlog or its viewer — stories not showing up, wrong/unknown statuses, malformed metadata, or anything that looks broken. Use when the user reports symptoms like "no stories show", "the viewer looks wrong", "status shows as Unknown", or generally "something seems broken" with the backlog.
---

<!--
local-backlog — a local issue/story tracker for Claude Code, no cloud account needed
Copyright (C) 2026  lbecjx

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version. See LICENSE for the full text.
-->

# Fix

Diagnoses a reported problem with the backlog or its viewer, applies the fix if
it's safe and unambiguous, and asks before touching anything that isn't.

## When to use

- The human reports a symptom: no stories show up, statuses show as "Unknown"
  or look wrong, cards look broken, search/filter behaves oddly, or anything
  else that looks like a malfunction rather than a feature request
- `/local-backlog:open-backlog` was just run and the result looks wrong

## When NOT to use

- To create a story → use `/local-backlog:create-story`
- To just open the viewer with no reported problem → use `/local-backlog:open-backlog`

## Scope boundary

This skill lives entirely on the side of the project that **consumes** the
plugin — its own `backlog/` folder, its own server process, its own story
files. It never touches or assumes anything about the separate
`backlog-viewer` development repo — same boundary `open-backlog` already
respects (see its own "Notes" section). If the viewer's actual *code* is
broken (not the data it's reading), that's a bug report for `backlog-viewer`,
not something this skill patches around.

This skill never edits a story's body content — only its metadata table.

## Execution

### Step 1: Understand the symptom

If the human's report is vague ("something's off"), ask what exactly they see
— a blank list, wrong statuses, a specific story missing, a visual glitch.
Don't start guessing before you know what "broken" means here.

### Step 2: Run the checklist (cheapest checks first)

1. **Does `backlog/` exist at the repo root?** (`git rev-parse --show-toplevel`,
   then check for the folder). If not, there's nothing to fix — tell the human
   and suggest `/local-backlog:create-story`.
2. **Is the local server actually running and responding?** Check for a
   `.viewer.pid` in the staging directory (see `open-backlog`'s own Step 4 for
   how that's computed) and `curl` the URL. A dead or never-started server
   looks identical to "no stories" in the browser — rule this out first, it's
   the cheapest check.
3. **Is there a stray `index.html` (or any other file) inside `backlog/` that
   isn't a story?** `python3 -m http.server` serves that instead of the
   directory listing the viewer depends on for discovery — a single stray file
   silently breaks discovery for every story in the folder. This exact bug
   was found and fixed in a real project during this skill's design (a leftover
   `index.html` from a discontinued generator).
4. **Do the story files use the current metadata schema?** The table must
   read `| Field | Value |` with rows `Code / Type / Priority / Status /
   Labels / Created / Updated` (see `create-story/references/template.md` for
   the authoritative current shape). Grep for the table header row across
   `backlog/*.md` — any file whose table doesn't match (legacy Spanish keys
   like `Campo/Valor`, `Estado`, `Código`, or any other drift) is why the
   viewer shows "Unknown" or blank fields for it: the parser reads the
   current English keys only, nothing else.

### Step 3: Handle each finding

- **Unambiguous, safe fix** (rename legacy metadata keys to current ones,
  delete a stray non-story file blocking discovery) → show the human exactly
  what you're about to change — the diff or a clear before/after — and get
  confirmation before applying. Never bulk-edit every story file silently,
  even when the fix is mechanical and applies to all of them the same way.
  If the fix changes a story's `Status` value (not just renames the field
  key), use `/local-backlog:update-status`'s script instead of editing the
  `Status` row directly — it keeps `Updated` and `## History` in sync in the
  same pass, which a manual edit here would otherwise skip.
- **Ambiguous** (a status value that isn't a known state and isn't clearly a
  deliberate custom one either, a field that doesn't map cleanly to the
  current schema, anything you'd have to guess at) → ask the human what they
  want instead of inventing an answer.

### Step 4: Escalate if the checklist doesn't explain it

If everything above checks out clean but the human still reports a problem,
this isn't a data/format issue — it needs real investigation. Launch a
general-purpose subagent to dig further (read the actual served HTML/JS, walk
the browser console if available, compare the real files against what
`discoverStories`/`parseStory` in the viewer's source actually expect). Don't
reach for a subagent as the first move — only once the cheap checklist in
Step 2 is exhausted.

### Step 5: Report

Tell the human what was found, what was fixed (and confirmed), and anything
still open that needs their decision. Keep it concrete — cite the actual file
and the actual problem, not a generic "fixed some issues."
