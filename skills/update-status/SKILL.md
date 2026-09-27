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
actual convention. The statuses are **canonical** — defined once in the story
model (`skills/create-story/references/story-model.json`, under
`x-story-file.enums.status`), shared by the plugin and the viewer:
`"Not Started"`, `"In Progress"`, `"Done"`, `"Blocked"`. There is no
per-project status list to edit. Prefer one of those over inventing new
wording. Show what's about to change:

```
[CODE]: Not Started → Done
```

For an unambiguous case (human explicitly named the story and the target
status) this confirmation can be a statement rather than a question — don't
turn an explicit instruction into an extra round-trip.

### Step 3: If the story is being started, offer the start setup

"Starting to work on a story" is two moves that otherwise live in separate
places: set the story `In Progress`, and put it on the Planner board. Offer both
here, so the board doesn't silently drift behind the status.

First see where the story stands: its current `Status` (Step 2 already showed
it) and its board zone —

```bash
bash "${CLAUDE_PLUGIN_ROOT}/skills/update-status/scripts/get-board.sh" <path-to-story-file>
```

which prints `backlog`, `planner`, or `archive`. Then **skip the question** when
it wouldn't be meaningful:

- the zone is **`archive`** — a status or board change there is wrong;
- the story is already `In Progress` **and** on `planner` — nothing left to offer;
- the human is **closing** the story (target `Done` or `Blocked`), not starting it.

Otherwise ask **once**, with the question tool, a single question carrying only
the parts still missing, with **"Yes" as the default** (list it first):

```
[CODE]: set up for work?
  (a) Status → In Progress        [Yes] [No]   (omit if already In Progress)
  (b) Add to the Planner board    [Yes] [No]   (omit if already on Planner)
```

Apply each accepted part with its own script — never silently:

- **(a)** is the normal status change: make `In Progress` the target status and
  let Step 5 write it once (don't run the script twice).
- **(b)** is a **zone-only** write that must **not** touch `Status`:
  `bash "${CLAUDE_PLUGIN_ROOT}/skills/update-status/scripts/set-board.sh" <path-to-story-file> planner`.

A declined part is left exactly as it was. When nobody can answer (unattended),
don't guess at the board — skip the offer and just do the explicit status change
the human asked for.

### Step 4: If the target is Done, gather the resolution first

`Done` also carries a *resolution*: which canonical outcome closed the story.
The resolution values live in the same story model, under
`x-story-file.enums.resolution` (`Done`, `Won't Do`, `Duplicate`,
`Cannot Reproduce`). A move to `Done` **requires** one — the script refuses
without it.

When a human is in the loop, **they choose the resolution** — ask with the
question tool, offering the canonical values, rather than guessing:

1. Which resolution applies.
2. An optional `note` — one short line of *why* (the resolution says *which*,
   the note says *why*) — offering "skip" as a valid answer.

Pass both to the script in Step 5. When running **unattended** (nobody to
ask — e.g. an automated archive), pick the most fitting canonical resolution
yourself and write a one-line `note` explaining the choice, so the decision
isn't silent.

Moving **out of** `Done` is the opposite: no resolution applies, so don't
ask and don't pass one — the script clears the stored `Resolution` and `Note`
rows.

### Step 5: Run the script

```bash
bash "${CLAUDE_PLUGIN_ROOT}/skills/update-status/scripts/update-status.sh" <path-to-story-file> "<new-status>" [--resolution "<value>"] [--note "<text>"]
```

This does all the writes together, from a real clock:
- Updates the `| **Status** |` row
- Sets the `| **Resolution** |` and `| **Note** |` rows — a value when moving
  into `Done`, empty otherwise — inserting those rows after `Status` if the
  story predates them
- Updates the `| **Updated** |` row to the same date
- Appends `- YYYY-MM-DDTHH:MM:SSZ — Status: <old> → <new>` to `## History`

Never hand-edit these spots separately — that's exactly the kind of
multi-location update that drifts (a `Status` change without the matching
`History` line, or vice versa). If the script reports "nothing to do" (the
requested status matches the current one), relay that as-is — don't treat it
as a failure.

**If the script exits non-zero because a value isn't canonical** — the
requested status, or the resolution when moving to `Done` (it prints the
actual list in both cases): don't silently pick the closest one, and don't
retry with a different value on your own. Show the human the list the script
printed and ask which they meant. Both lists are **canonical** — defined once
in the story model (`skills/create-story/references/story-model.json`, under
`x-story-file.enums.status` and `x-story-file.enums.resolution`), shared by
the plugin and the viewer; there is no per-project list to edit.

A move to `Done` with **no** resolution at all is the same kind of error
(exit 2): ask the human which resolution applies (Step 4) and re-run with
it — never pass a placeholder to get past the check.

### Step 6: Report

Relay the script's own output — it already states the old/new status and the
exact line it appended. Don't paraphrase the timestamp into your own summary:
the stored value is UTC for a viewer to format later, not for display as-is,
and re-deriving a "nicer" local-time line by hand is how these things go
stale or wrong.

## Principles

- **One script, one atomic update** — `Status`, `Resolution`, `Note`,
  `Updated`, and `History` change together or not at all; never edit just some
  of them by hand.
- **Resolution is the human's call** — for a move to `Done`, the human picks
  which canonical resolution applies; choose it yourself only when
  unattended, and write a `note` so the choice isn't silent.
- **Real clock, not a guess** — the timestamp always comes from `date -u`
  inside the script, never typed or estimated.
- **History is append-only** — past entries are never edited or removed, even
  to "correct" a mistaken transition; append a new line showing the real
  correction instead.
