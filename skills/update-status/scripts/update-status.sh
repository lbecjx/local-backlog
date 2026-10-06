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
# Status does not change, no History line is added, and any existing Note is
# left untouched — so the invariant `Status: Done ⇒ Resolution set` holds
# without inventing a transition.
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
LOCK_POLL=0.05       # seconds between attempts
LOCK_MAX_TRIES=200   # 200 × 0.05s — the 10s the timeout message states
LOCK_WAIT=0
until mkdir "$LOCK_DIR" 2>/dev/null; do
  sleep "$LOCK_POLL"
  LOCK_WAIT=$((LOCK_WAIT + 1))
  if [[ "$LOCK_WAIT" -ge "$LOCK_MAX_TRIES" ]]; then
    echo "Could not acquire lock on $STORY_FILE after 10s — another update may be stuck" >&2
    exit 1
  fi
done
# One cleanup for everything this run holds — the lock and the temp file below —
# on every exit path and on INT/TERM. A leaked `<story>.lock` makes every later
# update of that story wait out the 10s timeout above until someone removes it.
# The rmdir is best-effort: there is nothing useful to do if it fails. INT/TERM
# exit with 128+signal so the EXIT trap runs `release` and callers still see the
# signal. The trap goes in after the lock is taken, on purpose — installed before,
# a run that timed out would remove another run's lock; so a signal in the few
# instructions between `mkdir` and here can still leak the lock. Closing that fully
# would mean masking signals around every lock attempt; SIGKILL can leak it anyway.
CUR_TMP=""
release() {
  [[ -n "$CUR_TMP" ]] && rm -f "$CUR_TMP"
  rmdir "$LOCK_DIR" 2>/dev/null
}
trap release EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# Where the temp file goes. Next to the story (same filesystem, so the final `mv`
# is an atomic rename) — but only when that folder is positively private: owned by
# the user and not writable by group or others. Anywhere else someone could swap
# the temp file for a symlink between `mktemp` and the write, and the write would
# land in whatever file it points at. So the test fails closed (a `find` error, a
# folder owned by someone else, an ACL it cannot see all fall through) to $TMPDIR,
# a per-user directory, at the cost of a non-atomic move.
# Neither name ends in `.md`, so no `*.md` glob (this plugin's, the viewer's) sees it.
temp_template() {
  local dir
  dir=$(dirname "$1")
  if [[ -n "$(find "$dir" -maxdepth 0 -user "$(id -u)" ! -perm -020 ! -perm -002 2>/dev/null)" ]]; then
    echo "$1.XXXXXX"
  else
    echo "${TMPDIR:-/tmp}/$(basename "$1").XXXXXX"
  fi
}

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

# An archived story is frozen: the only way to change anything about it is to
# unarchive it first (set-zone.sh ... backlog|planner). Archiving is the human's
# explicit action (the viewer's Archive button, never a status change); this
# guard is what stops a later status write from silently rewriting a story that
# was meant to be closed and out of the way. Read from the story's own
# `| **Zone** |` row (the value get-zone.sh reads), inside the lock, so a
# concurrent unarchive cannot slip between this check and the write below. A
# missing or unrecognized row reads as `backlog` — the same fail-open default
# used everywhere zone is read. `tr` (not bash 4's ${v,,}) because macOS ships
# bash 3.2.
STORY_ZONE=$(grep -m1 '^| \*\*Zone\*\* |' "$STORY_FILE" | sed -E 's/^\| \*\*Zone\*\* \| *//; s/ *\|$//')
if [[ "$(printf '%s' "$STORY_ZONE" | tr '[:upper:]' '[:lower:]')" == "archive" ]]; then
  echo "$STORY_FILE is archived — unarchive it first (set-zone.sh \"$STORY_FILE\" backlog|planner); an archived story accepts no changes." >&2
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
# On a backfill the note has no transition to attach to, so an existing one must
# survive: overwriting it here would destroy the story's current note with no
# History line recording what it was. A note passed alongside a backfill is
# therefore only used to fill a row that is still empty.
if [[ "$BACKFILL" == "1" && -n "$OLD_NOTE" ]]; then
  EFFECTIVE_NOTE="$OLD_NOTE"
fi

# `mktemp` creates the file 0600 and `mv` would carry that onto the story, so the
# story's mode is read now and put back on the temp file just before the move. It
# is carried by value (`chmod`), not with `cp -p`: on macOS `cp -p` also copies file
# flags, and an immutable story would yield an immutable temp file that the
# cleanup could not remove. GNU `stat -c` is tried first because BSD `stat` takes
# `-f` for the format, where GNU `-f` means something else and exits 0.
# Signals are ignored (not deferred) for the two lines that create the temp file and
# record it, so an interrupt can't land between them and strand it.
trap '' INT TERM
if ! TMP_FILE=$(mktemp "$(temp_template "$STORY_FILE")"); then
  trap 'exit 130' INT
  trap 'exit 143' TERM
  echo "Failed to create a temp file for $STORY_FILE — left unchanged." >&2
  exit 1
fi
CUR_TMP="$TMP_FILE"
trap 'exit 130' INT
trap 'exit 143' TERM
if ! ORIG_MODE=$(stat -c %a "$STORY_FILE" 2>/dev/null || stat -f %Lp "$STORY_FILE" 2>/dev/null); then
  echo "Failed to read the file mode of $STORY_FILE — left unchanged." >&2
  exit 1
fi

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
  # A wrapped continuation line of the entry above — indented, so it is neither
  # a new `- ` entry nor the blank line that ends the block. Print it and keep
  # the section open. Without this rule the branch below fired on the FIRST
  # continuation line instead: it appended the new transition there (splitting
  # the old entry in two) and `next`ed without printing, so the continuation
  # line was DELETED. Reproduced 2026-10-05 against an LB-0016 History block —
  # real data loss, and the whole point of this plugin is that a status change
  # never loses story content.
  in_history && saw_entry && $0 != "" && /^[[:space:]]/ { print; next }
  in_history && saw_entry {
    # The entry block ended without a blank line after it — a trailing `---`,
    # another heading, anything. Append the new line HERE, before that line,
    # rather than dropping it or letting it land outside `## History`. There is
    # deliberately no `next`: matching this branch means the line here is that
    # terminator, and the old `next` dropped it — the same bug that ate a
    # continuation line, one level up.
    if (history_line != "") print history_line
    in_history = 0
  }
  in_history && $0 != "" {
    # Same, for a section that has NO entry yet (a malformed story). `saw_entry`
    # is deliberately not required here: past the heading, a non-blank line means
    # the section is over, so this can never fire on the blank line that merely
    # precedes the first real entry.
    if (history_line != "") print history_line
    in_history = 0
  }
  { print }
  END {
    # The `## History` block ran to the end of the file with no blank line and no
    # following line to trigger either append above.
    if (in_history && history_line != "") print history_line
  }
' "$STORY_FILE" > "$TMP_FILE"; then
  echo "Failed to rewrite $STORY_FILE — left unchanged." >&2
  exit 1
fi

if ! chmod "$ORIG_MODE" "$TMP_FILE"; then
  echo "Failed to set the file mode on the rewritten $STORY_FILE — left unchanged." >&2
  exit 1
fi

# The move is checked too: an unwritable target (e.g. an immutable story file)
# would otherwise leave the story unchanged while the script still reported
# success and printed the transition.
if ! mv "$TMP_FILE" "$STORY_FILE"; then
  echo "Failed to write $STORY_FILE — left unchanged." >&2
  exit 1
fi
CUR_TMP=""

if [[ "$BACKFILL" == "1" ]]; then
  echo "Resolution: ${RESOLUTION} (backfilled; Status unchanged: ${NEW_STATUS})"
else
  echo "Status: ${OLD_STATUS} → ${NEW_STATUS}"
  [[ -n "$RESOLUTION" ]] && echo "Resolution: ${RESOLUTION}"
  echo "Appended: ${HISTORY_LINE}"
fi
