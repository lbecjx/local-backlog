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
# Usage: update-status.sh <story-file> <new-status>
# Prints the old and new status, and the exact History line appended.

STORY_FILE="$1"
NEW_STATUS="$2"

if [[ -z "$STORY_FILE" || -z "$NEW_STATUS" ]]; then
  echo "Usage: update-status.sh <story-file> <new-status>" >&2
  exit 1
fi

if [[ ! -f "$STORY_FILE" ]]; then
  echo "No such file: $STORY_FILE" >&2
  exit 1
fi

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

if [[ -z "$OLD_STATUS" ]]; then
  echo "Could not find a '| **Status** | ... |' row in $STORY_FILE — is this a story file created from the current template?" >&2
  exit 1
fi

if [[ "$OLD_STATUS" == "$NEW_STATUS" ]]; then
  echo "Status is already '$OLD_STATUS' — nothing to do."
  exit 0
fi

# `.backlog-statuses.json` living alongside the story file (a separate file
# from `.backlog-config.json`, which is only about ticket numbering — prefix
# and lastCode, unrelated to Status) is the closest thing this project has to
# a type for Status: if it exists, its list is closed — an unlisted value is
# rejected rather than silently accepted (a typo would otherwise pass right
# through, string comparisons being case- and spelling-sensitive). No such
# file means the project hasn't opted into this — any string is accepted,
# same as before this existed.
STATUSES_FILE="$(dirname "$STORY_FILE")/.backlog-statuses.json"
if [[ -f "$STATUSES_FILE" ]]; then
  KNOWN_STATUSES=$(grep -o '"name"[[:space:]]*:[[:space:]]*"[^"]*"' "$STATUSES_FILE" | sed -E 's/.*"([^"]*)"$/\1/')
  if ! grep -qxF "$NEW_STATUS" <<< "$KNOWN_STATUSES"; then
    echo "'$NEW_STATUS' isn't one of the statuses defined in $STATUSES_FILE:" >&2
    echo "$KNOWN_STATUSES" | sed 's/^/  - /' >&2
    echo "Use one of the above, or add \"$NEW_STATUS\" to that file's \"statuses\" list first." >&2
    # Exit 2, not the generic 1 every other failure in this script uses —
    # this one specifically means "the caller asked for an invalid value,"
    # not "something went wrong on this end" (a missing file, a stuck lock,
    # a malformed story). A caller relaying this over HTTP (idle_server.py)
    # uses this distinction to answer with a 400 instead of a 500 — the
    # difference between a bad request and a server-side failure.
    exit 2
  fi
fi

if ! grep -q '^## History$' "$STORY_FILE"; then
  echo "No '## History' section found in $STORY_FILE — this story predates that template section. Add one manually first (see skills/create-story/references/template.md), then re-run this." >&2
  exit 1
fi

NOW_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)
TODAY="${NOW_UTC%%T*}"
HISTORY_LINE="- ${NOW_UTC} — Status: ${OLD_STATUS} → ${NEW_STATUS}"

TMP_FILE=$(mktemp)

awk -v new_status="$NEW_STATUS" -v today="$TODAY" -v history_line="$HISTORY_LINE" '
  /^\| \*\*Status\*\* \|/ { print "| **Status** | " new_status " |"; next }
  /^\| \*\*Updated\*\* \|/ { print "| **Updated** | " today " |"; next }
  /^## History$/ { print; in_history = 1; next }
  in_history && /^- / { print; saw_entry = 1; next }
  in_history && saw_entry && $0 == "" {
    print history_line
    print
    in_history = 0
    next
  }
  { print }
' "$STORY_FILE" > "$TMP_FILE"

mv "$TMP_FILE" "$STORY_FILE"

echo "Status: ${OLD_STATUS} → ${NEW_STATUS}"
echo "Appended: ${HISTORY_LINE}"
