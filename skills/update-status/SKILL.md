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
here, so the `Zone` field doesn't silently drift behind the status.

First see where the story stands: its current `Status` (Step 2 already showed
it) and its `Zone` —

```bash
bash "${CLAUDE_PLUGIN_ROOT}/skills/update-status/scripts/get-zone.sh" <path-to-story-file>
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
  let Step 6 write it once (don't run the script twice). If (a) is **declined**,
  the target stays the story's current status — Step 6 must not write `In
  Progress` in that case. A declined status change is never applied.
- **(b)** is a **zone-only** write that must **not** touch `Status`:
  `bash "${CLAUDE_PLUGIN_ROOT}/skills/update-status/scripts/set-zone.sh" <path-to-story-file> planner`.

A declined part is left exactly as it was. When nobody can answer (unattended),
don't guess at the zone — skip the offer and just do the explicit status change
the human asked for.

### Step 4: If the target is Done, gather the resolution first

`Done` also carries a *resolution*: which canonical outcome closed the story.
The resolution values live in the same story model, under
`x-story-file.enums.resolution` (`Done`, `Won't Do`, `Duplicate`,
`Cannot Reproduce`). A move to `Done` **requires** one — the script refuses
without it.

When a human is in the loop, **they choose the resolution** — ask with the
question tool, offering the canonical values, rather than guessing. Pass it to
the script in Step 6. When running **unattended** (nobody to ask — e.g. an
automated archive), pick the most fitting canonical resolution yourself, so the
decision isn't silent.

Moving **out of** `Done` is the opposite: no resolution applies, so don't
ask and don't pass one — the script clears the stored `Resolution` and `Note`
rows.

The *why* is not asked here: it is the note, and it applies to every
transition — see Step 5.

### Step 5: Gather the note (any transition)

Any status change may carry an optional one-line note of *why* — the
resolution says *which* outcome closed the story, the note says *why* it
moved. It is deliberately the **same concept for every transition**, `Done`
included; there is no separate "reason" that only applies to archiving.

When a human is in the loop, ask **once**, with the question tool, offering
**skip** as a valid answer:

```
[CODE]: note for this change?   (optional — one short line)
```

The note is never required, for any target status: a skipped note is simply no
note — the transition still goes through, and the story's `Note` row ends up
empty because *this* change carries nothing to say (see the `Note` row's own
wording in `skills/create-story/references/template.md`). Pass whatever the
human gave to the script in Step 6.

When running **unattended** (nobody to ask), don't leave it blank: infer a
short note from the transition itself — why the story moved, in one line — and
write it, so the change doesn't land silently. Same rule as the resolution
above, for the same reason.

### Step 6: Run the script

```bash
bash "${CLAUDE_PLUGIN_ROOT}/skills/update-status/scripts/update-status.sh" <path-to-story-file> "<new-status>" [--resolution "<value>"] [--note "<text>"]
```

This does all the writes together, from a real clock:
- Updates the `| **Status** |` row
- Sets the `| **Resolution** |` and `| **Note** |` rows — `Resolution` when
  moving into `Done`, the `Note` from this transition, empty otherwise —
  inserting those rows after `Status` if the story predates them
- Updates the `| **Updated** |` row to the same date
- Appends `- YYYY-MM-DDTHH:MM:SSZ — Status: <old> → <new>` to `## History`,
  with ` · Resolution: <value>` and then ` · Note: <text>` appended when the
  transition carries them — so each earlier transition keeps its own reason,
  which the single `Note` row above cannot

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

### Step 7: Report

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
  unattended, so the decision isn't silent.
- **The note is optional for a human, never blank unattended** — on any
  transition a human may skip it, and skipping writes no note at all (never
  invent one they declined); with nobody to ask, the agent infers a one-line
  note and writes it, so the change isn't silent. Optional and unattended are
  not in conflict: they are the two halves of the same rule.
- **Real clock, not a guess** — the timestamp always comes from `date -u`
  inside the script, never typed or estimated.
- **History is append-only** — past entries are never edited or removed, even
  to "correct" a mistaken transition; append a new line showing the real
  correction instead.
