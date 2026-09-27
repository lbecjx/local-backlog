#!/bin/bash
# local-backlog — a local issue/story tracker for Claude Code, no cloud account needed
# Copyright (C) 2026  lbecjx
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version. See LICENSE for the full text.

# Updates a story's Status field, Updated field, and appends a line to its
# History section — all three in one atomic step, from a real clock, so they
# can never drift out of sync with each other. This is exact, mechanical
# bookkeeping: a script gets the timestamp and the line insertion right every
# time; a model hand-editing three separate spots in a markdown file is
# exactly the kind of task that drifts.
#
# Usage: update-status.sh <story-file> <new-status> [--resolution <value>] [--note <text>] [--expect <status>]
# Prints the old and new status, and the exact History line appended.
# --resolution is required when moving into Done (from the canonical model) and
# is written to the story's `Resolution` row (emptied when leaving Done).
# --note is the optional free-text for the transition, written to the `Note` row.
# Both also ride on the History line this script appends, after the new status
# (` · Resolution: <value>`, then ` · Note: <text>`), so the transition's own
# reason survives the next transition overwriting the single `Note` row.
# A story already at Done with an empty Resolution is the legacy gap from before
# the field existed: asking for it with --resolution fills only that row — the
# Status does not change and no History line is added — so the invariant
# `Status: Done ⇒ Resolution set` holds without inventing a transition.
# With --expect, the change applies only if the story's current status still
# equals <status> — a compare-and-swap evaluated and written inside the same
# lock, so it can't race a concurrent write. Exit 3 = precondition failed (the
# status moved on); nothing is written.

STORY_FILE="$1"
NEW_STATUS="$2"
shift 2 2>/dev/null || true

EXPECT=""
RESOLUTION=""
NOTE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --expect)
      if [[ $# -lt 2 ]]; then
        echo "--expect requires a value" >&2
        exit 1
      fi
      EXPECT="$2"; shift 2 ;;
    --resolution)
      if [[ $# -lt 2 ]]; then
        echo "--resolution requires a value" >&2
        exit 1
      fi
      RESOLUTION="$2"; shift 2 ;;
    --note)
      if [[ $# -lt 2 ]]; then
        echo "--note requires a value" >&2
        exit 1
      fi
      NOTE="$2"; shift 2 ;;
    *) echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
done

if [[ -z "$STORY_FILE" || -z "$NEW_STATUS" ]]; then
  echo "Usage: update-status.sh <story-file> <new-status> [--resolution <value>] [--note <text>] [--expect <status>]" >&2
  exit 1
fi

if [[ ! -f "$STORY_FILE" ]]; then
  echo "No such file: $STORY_FILE" >&2
  exit 1
fi

# Each of these ends up inside one markdown table cell, so a raw newline (which
# would also have made the awk below fail fatally) or a `|` (which would split
# the row) is refused up front, before the lock is taken or anything is
# written. Exit 2, the same "the caller asked for a bad value" code the status/
# resolution checks below use, so an HTTP caller relays it as a 400.
reject_bad_value() {
  if [[ "$2" == *$'\n'* || "$2" == *$'\r'* || "$2" == *"|"* ]]; then
    echo "$1 must be a single line, with no newline or '|' character." >&2
    exit 2
  fi
}
reject_bad_value status "$NEW_STATUS"
reject_bad_value resolution "$RESOLUTION"
reject_bad_value note "$NOTE"

# `mkdir` is atomic on any POSIX filesystem, which makes it a portable
# mutex with no extra tooling (no `flock` CLI on macOS, and this script
# stays plain bash/awk rather than pulling in python3 just for locking).
# Needed because this script's own local server can now trigger it from
# concurrent HTTP requests targeting the same story — without this, two
# near-simultaneous calls read the same pre-write file and one silently
# clobbers the other's History append.
LOCK_DIR="${STORY_FILE}.lock"
LOCK_WAIT=0
until mkdir "$LOCK_DIR" 2>/dev/null; do
  sleep 0.05
  LOCK_WAIT=$((LOCK_WAIT + 1))
  if [[ "$LOCK_WAIT" -ge 200 ]]; then
    echo "Could not acquire lock on $STORY_FILE after 10s — another update may be stuck" >&2
    exit 1
  fi
done
trap 'rmdir "$LOCK_DIR" 2>/dev/null' EXIT

OLD_STATUS=$(grep -m1 '^| \*\*Status\*\* |' "$STORY_FILE" | sed -E 's/^\| \*\*Status\*\* \| *(.*[^ ]) *\|$/\1/')
# Stripped in two steps (not the single `(.*[^ ])` capture the Status read uses)
# because an empty row like `| **Resolution** |  |` has no non-space value for
# that capture to match — it would leave the whole raw line behind, reading as
# non-empty. `s///`-then-`s///` yields "" for both an empty row and an absent one.
OLD_RESOLUTION=$(grep -m1 '^| \*\*Resolution\*\* |' "$STORY_FILE" | sed -E 's/^\| \*\*Resolution\*\* \| *//; s/ *\|$//')
OLD_NOTE=$(grep -m1 '^| \*\*Note\*\* |' "$STORY_FILE" | sed -E 's/^\| \*\*Note\*\* \| *//; s/ *\|$//')

if [[ -z "$OLD_STATUS" ]]; then
  echo "Could not find a '| **Status** | ... |' row in $STORY_FILE — is this a story file created from the current template?" >&2
  exit 1
fi

# Compare-and-swap precondition (see --expect above): checked here, inside the
# lock, so no concurrent write can slip between this check and the write below.
if [[ -n "$EXPECT" && "$OLD_STATUS" != "$EXPECT" ]]; then
  echo "changed concurrently: expected '$EXPECT' but found '$OLD_STATUS' — not applying" >&2
  exit 3
fi

# A repeated status is normally a no-op, with one exception: a story already at
# Done with no Resolution is the legacy gap (it reached Done before the field
# existed). Asking for it with --resolution fills that gap — not a transition,
# just the missing field. Any other repeated status stays a no-op.
BACKFILL=0
if [[ "$OLD_STATUS" == "$NEW_STATUS" ]]; then
  if [[ "$NEW_STATUS" == "Done" && -n "$RESOLUTION" && -z "$OLD_RESOLUTION" ]]; then
    BACKFILL=1
  else
    echo "Status is already '$OLD_STATUS' — nothing to do."
    exit 0
  fi
fi

# Status values are canonical now: they live in the story model (the single
# source), not in a per-project file. The model is read with python3 — already
# a hard dependency of this plugin — because it is nested JSON, where grep/sed
# would be fragile. An unlisted value is rejected rather than silently accepted
# (a typo would otherwise pass right through, string comparisons being case-
# and spelling-sensitive).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODEL_FILE="$SCRIPT_DIR/../../create-story/references/story-model.json"
if [[ ! -f "$MODEL_FILE" ]]; then
  echo "Story model not found at $MODEL_FILE — the plugin install looks incomplete." >&2
  exit 1
fi
KNOWN_STATUSES=$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print("\n".join(v["name"] for v in d["x-story-file"]["enums"]["status"]["values"]))' "$MODEL_FILE")
# `--` ends grep's option parsing: without it a value shaped like an option
# (`--version`, `-eDone`) is taken as a flag, grep exits 0, and the value slips
# through the canonical-set gate below.
if ! grep -qxF -- "$NEW_STATUS" <<< "$KNOWN_STATUSES"; then
  echo "'$NEW_STATUS' isn't one of the canonical statuses:" >&2
  echo "$KNOWN_STATUSES" | sed 's/^/  - /' >&2
  echo "Use one of the above." >&2
  # Exit 2, not the generic 1 every other failure in this script uses —
  # this one specifically means "the caller asked for an invalid value,"
  # not "something went wrong on this end" (a missing file, a stuck lock,
  # a malformed story). A caller relaying this over HTTP (idle_server.py)
  # uses this distinction to answer with a 400 instead of a 500 — the
  # difference between a bad request and a server-side failure.
  exit 2
fi

# Resolution is required when entering Done, and must be one of the canonical
# values (same model, a different enum). Leaving Done needs no resolution and
# clears the row (below). Passing --resolution for a non-Done target is a
# caller error, not silently ignored.
if [[ "$NEW_STATUS" == "Done" ]]; then
  if [[ -z "$RESOLUTION" ]]; then
    echo "Moving to 'Done' requires --resolution <value>." >&2
    exit 2
  fi
  KNOWN_RESOLUTIONS=$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print("\n".join(d["x-story-file"]["enums"]["resolution"]["values"]))' "$MODEL_FILE")
  if ! grep -qxF -- "$RESOLUTION" <<< "$KNOWN_RESOLUTIONS"; then
    echo "'$RESOLUTION' isn't one of the canonical resolutions:" >&2
    echo "$KNOWN_RESOLUTIONS" | sed 's/^/  - /' >&2
    exit 2
  fi
elif [[ -n "$RESOLUTION" ]]; then
  echo "--resolution only applies when moving to 'Done'." >&2
  exit 1
fi

if ! grep -q '^## History$' "$STORY_FILE"; then
  echo "No '## History' section found in $STORY_FILE — this story predates that template section. Add one manually first (see skills/create-story/references/template.md), then re-run this." >&2
  exit 1
fi

NOW_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)
TODAY="${NOW_UTC%%T*}"
# A backfill is not a transition, so it appends no History line (the `## History`
# log stays a log of status changes only) and preserves any existing Note.
if [[ "$BACKFILL" == "1" ]]; then
  HISTORY_LINE=""
else
  HISTORY_LINE="- ${NOW_UTC} — Status: ${OLD_STATUS} → ${NEW_STATUS}"
  # The transition's own resolution (only ever on a move into Done) and its
  # optional note ride on the same line, in that order. The `Note` row alone
  # can't hold a per-transition note: it is a single cell the next transition
  # overwrites, so the `## History` line is the only place a note stays
  # attached to the transition that produced it.
  if [[ -n "$RESOLUTION" ]]; then
    HISTORY_LINE="${HISTORY_LINE} · Resolution: ${RESOLUTION}"
  fi
  if [[ -n "$NOTE" ]]; then
    HISTORY_LINE="${HISTORY_LINE} · Note: ${NOTE}"
  fi
fi
EFFECTIVE_NOTE="$NOTE"
if [[ "$BACKFILL" == "1" && -z "$NOTE" ]]; then
  EFFECTIVE_NOTE="$OLD_NOTE"
fi

TMP_FILE=$(mktemp)

# The values are passed through the environment, not awk -v: -v runs each
# through awk's own escape processing, so a backslash in a note (e.g. a Windows
# path) was silently turned into a newline/tab and split the metadata table.
# ENVIRON values are opaque byte strings. The single-line check above already
# keeps a raw newline out of the program text entirely. The exit status is
# checked before the move so an awk failure can never overwrite the story with
# the empty temp file.
if ! NEW_STATUS="$NEW_STATUS" TODAY="$TODAY" HISTORY_LINE="$HISTORY_LINE" RESOLUTION="$RESOLUTION" NOTE="$EFFECTIVE_NOTE" awk '
  BEGIN {
    new_status = ENVIRON["NEW_STATUS"]
    today = ENVIRON["TODAY"]
    history_line = ENVIRON["HISTORY_LINE"]
    resolution = ENVIRON["RESOLUTION"]
    note = ENVIRON["NOTE"]
  }
  /^\| \*\*Status\*\* \|/ {
    print "| **Status** | " new_status " |"
    print "| **Resolution** | " resolution " |"
    print "| **Note** | " note " |"
    next
  }
  /^\| \*\*Resolution\*\* \|/ { next }
  /^\| \*\*Note\*\* \|/ { next }
  /^\| \*\*Updated\*\* \|/ { print "| **Updated** | " today " |"; next }
  /^## History$/ { print; in_history = 1; next }
  in_history && /^- / { print; saw_entry = 1; next }
  in_history && saw_entry && $0 == "" {
    if (history_line != "") print history_line
    print
    in_history = 0
    next
  }
  { print }
' "$STORY_FILE" > "$TMP_FILE"; then
  rm -f "$TMP_FILE"
  echo "Failed to rewrite $STORY_FILE — left unchanged." >&2
  exit 1
fi

# The move is checked too: an unwritable target (e.g. an immutable story file)
# would otherwise leave the story unchanged while the script still reported
# success and printed the transition.
if ! mv "$TMP_FILE" "$STORY_FILE"; then
  rm -f "$TMP_FILE"
  echo "Failed to write $STORY_FILE — left unchanged." >&2
  exit 1
fi

if [[ "$BACKFILL" == "1" ]]; then
  echo "Resolution: ${RESOLUTION} (backfilled; Status unchanged: ${NEW_STATUS})"
else
  echo "Status: ${OLD_STATUS} → ${NEW_STATUS}"
  [[ -n "$RESOLUTION" ]] && echo "Resolution: ${RESOLUTION}"
  echo "Appended: ${HISTORY_LINE}"
fi
