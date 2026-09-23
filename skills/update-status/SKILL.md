---
name: update-status
description: Changes a story's Status field, updates its Updated field, and appends the transition to its History section — all three kept in sync automatically. Use when the user says "mark <CODE> as done", "start working on <CODE>", "move <CODE> to in progress", or otherwise wants a story's Status changed.
---

<!--
local-backlog — a local issue/story tracker for Claude Code, no cloud account needed
Copyright (C) 2026  lbecjx

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version. See LICENSE for the full text.
-->

# Update Status

Moves a story to a new `Status`, keeping the metadata table and the
`## History` section consistent — the two must never drift apart, so a
script does both writes in one pass instead of an agent hand-editing each
one separately.

## When to use

- The human wants a story's `Status` changed — starting work, marking it
  done, blocking it, or moving it to any other value
- Work on a story (through whatever process the project uses to implement
  it) just finished, and its backlog file's `Status` should reflect that

## When NOT to use

- To create a story → use `/local-backlog:create-story`
- To repair a malformed or already-broken `Status` value → use
  `/local-backlog:fix` instead; that skill handles ambiguous/invalid data,
  this one handles a normal, intentional transition

## Execution

### Step 1: Identify the story file

Resolve `<CODE>` to its file under `local-backlog/` (e.g. `NB-0005` →
`local-backlog/NB-0005-*.md`) — glob on the code prefix, since the rest of the
filename is a free-text slug. Ask if more than one file matches or none do.

### Step 2: Confirm the target status

If the human said something like "mark it as done", map that to the story's
actual convention. The project's known statuses live in
`local-backlog/.backlog-config.json`'s `statuses` array — `"Not Started"`,
`"In Progress"`, `"Done"` are the 3 defaults every project starts with, but a
given project may have added more (e.g. `"Blocked"`). Prefer whatever's
already listed there over inventing new wording. Show what's about to
change:

```
[CODE]: Not Started → Done
```

For an unambiguous case (human explicitly named the story and the target
status) this confirmation can be a statement rather than a question — don't
turn an explicit instruction into an extra round-trip.

### Step 3: Run the script

```bash
bash "${CLAUDE_PLUGIN_ROOT}/skills/update-status/scripts/update-status.sh" <path-to-story-file> "<new-status>"
```

This does all three writes together, from a real clock:
- Updates the `| **Status** |` row
- Updates the `| **Updated** |` row to the same date
- Appends `- YYYY-MM-DDTHH:MM:SSZ — Status: <old> → <new>` to `## History`

Never hand-edit these three spots separately — that's exactly the kind of
multi-location update that drifts (a `Status` change without the matching
`History` line, or vice versa). If the script reports "nothing to do" (the
requested status matches the current one), relay that as-is — don't treat it
as a failure.

**If the script exits non-zero because the requested status isn't in the
project's `.backlog-statuses.json`** (it prints the actual list of known
statuses when this happens): don't silently pick the closest known one, and
don't retry with a different value on your own. Show the human the list the
script printed and ask which they meant — a genuine typo, or a real new
status this project should adopt. For a genuine new status, add an entry to
`.backlog-statuses.json`'s `statuses` array yourself, then re-run the script —
don't ask the human to hand-edit JSON. `color` must be one of the names
defined in `references/status-colors.json` (in this same skill folder) —
read that file rather than guessing or reusing a name from memory; it's the
same file `/local-backlog:open-backlog`'s viewer reads at runtime, so a name
not in it renders as an unstyled "unknown" status instead of the intended
color.

### Step 4: Report

Relay the script's own output — it already states the old/new status and the
exact line it appended. Don't paraphrase the timestamp into your own summary:
the stored value is UTC for a viewer to format later, not for display as-is,
and re-deriving a "nicer" local-time line by hand is how these things go
stale or wrong.

## Principles

- **One script, one atomic update** — `Status`, `Updated`, and `History` change
  together or not at all; never edit just one of the three by hand.
- **Real clock, not a guess** — the timestamp always comes from `date -u`
  inside the script, never typed or estimated.
- **History is append-only** — past entries are never edited or removed, even
  to "correct" a mistaken transition; append a new line showing the real
  correction instead.
