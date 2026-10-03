#!/bin/bash
# local-backlog — a local issue/story tracker for Claude Code, no cloud account needed
# Copyright (C) 2026  lbecjx
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version. See LICENSE for the full text.

# Updates a story's own `| **Zone** |` row (LB-0014: zone is a fact about
# the story, not a separate board file). Same locking/atomic-rewrite
# mechanism as update-status.sh, since this writes the same kind of file —
# a `mkdir`-based mutex (portable, no `flock` CLI needed on macOS) plus a
# `mktemp`+awk+`mv` atomic rewrite, not update-status.sh's own lock (a
# concurrent Status write and Zone write target the same story file but are
# two separate, sequential lock acquisitions from idle_server.py, never
# truly concurrent with each other).
#
# A zone change is not a Status transition: it never touches `## History`,
# mirroring today's set-board.sh (which never wrote History either).
#
# Usage: set-zone.sh <story-file> <backlog|planner|archive>
# Prints: Zone: <value>

STORY_FILE="$1"
ZONE="$2"
shift 2 2>/dev/null || true

if [[ -z "$STORY_FILE" || -z "$ZONE" ]]; then
  echo "Usage: set-zone.sh <story-file> <backlog|planner|archive>" >&2
  exit 1
fi

if [[ $# -gt 0 ]]; then
  echo "Unknown argument: $1" >&2
  exit 1
fi

if [[ ! -f "$STORY_FILE" ]]; then
  echo "No such file: $STORY_FILE" >&2
  exit 1
fi

# A story with neither row has nowhere for the insert branch below to
# anchor on — checked up front, before the lock or any write attempt, the
# same way update-status.sh refuses outright when its own anchor
# (`## History`) is missing, rather than letting a pattern silently match
# nothing. Without this, `awk` exits 0 having copied the file through
# unchanged, and this script would report success for a write that never
# happened — exactly the failure `/local-backlog:fix`'s `repair-missing-history.sh`
# exists to prevent for other legacy rows.
if ! grep -q '^| \*\*Zone\*\* |' "$STORY_FILE" && ! grep -q '^| \*\*Note\*\* |' "$STORY_FILE"; then
  echo "$STORY_FILE has neither a '| **Zone** |' nor a '| **Note** |' row to anchor on — this story predates both fields. Add a Note row first (see skills/create-story/references/template.md), then re-run this." >&2
  exit 1
fi

# Zone values are duplicated as literals in open-backlog/scripts/idle_server.py
# (VALID_ZONES, validated a second time before this script is ever invoked) —
# no shared source of truth across Python and bash, so keep both lists in
# sync by hand if either ever changes.
case "$ZONE" in
  backlog) ZONE_TITLE="Backlog" ;;
  planner) ZONE_TITLE="Planner" ;;
  archive) ZONE_TITLE="Archive" ;;
  *)
    echo "'$ZONE' is not a valid zone — must be one of: backlog, planner, archive" >&2
    exit 1
    ;;
esac

# Same mutex `update-status.sh` uses on this same story file — sequential
# acquisitions (archive does Status then Zone, one after the other from
# idle_server.py), never a simultaneous hold of the same lock by two
# in-flight writers.
LOCK_DIR="${STORY_FILE}.lock"
LOCK_POLL=0.05
LOCK_MAX_TRIES=200
LOCK_WAIT=0
until mkdir "$LOCK_DIR" 2>/dev/null; do
  sleep "$LOCK_POLL"
  LOCK_WAIT=$((LOCK_WAIT + 1))
  if [[ "$LOCK_WAIT" -ge "$LOCK_MAX_TRIES" ]]; then
    echo "Could not acquire lock on $STORY_FILE after 10s — another update may be stuck" >&2
    exit 1
  fi
done
CUR_TMP=""
release() {
  [[ -n "$CUR_TMP" ]] && rm -f "$CUR_TMP"
  rmdir "$LOCK_DIR" 2>/dev/null
}
trap release EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# Same private-directory check as update-status.sh's temp_template — falls
# back to $TMPDIR (at the cost of a non-atomic move) rather than risk a
# symlink swap in a world-writable directory.
temp_template() {
  local dir
  dir=$(dirname "$1")
  if [[ -n "$(find "$dir" -maxdepth 0 -user "$(id -u)" ! -perm -020 ! -perm -002 2>/dev/null)" ]]; then
    echo "$1.XXXXXX"
  else
    echo "${TMPDIR:-/tmp}/$(basename "$1").XXXXXX"
  fi
}

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

# Decided up front, not inside the single awk pass below: the Note row
# (where a missing Zone row gets inserted) always comes BEFORE the Zone row
# in a well-formed story, so a single forward pass can't tell "insert here"
# from "there's already one further down" without reading ahead. Checking
# first which case applies keeps the awk program a plain, unconditional
# replace-or-insert, with no risk of doing both for the same line.
# ZONE_TITLE is one of our own three literals (never free text from a
# caller), but it still goes through ENVIRON rather than awk -v, matching
# update-status.sh's own rule for every value it hands to awk.
if grep -q '^| \*\*Zone\*\* |' "$STORY_FILE"; then
  AWK_PROGRAM='/^\| \*\*Zone\*\* \|/ { print "| **Zone** | " ENVIRON["ZONE_TITLE"] " |"; next } { print }'
else
  AWK_PROGRAM='/^\| \*\*Note\*\* \|/ { print; print "| **Zone** | " ENVIRON["ZONE_TITLE"] " |"; next } { print }'
fi

if ! ZONE_TITLE="$ZONE_TITLE" awk "$AWK_PROGRAM" "$STORY_FILE" > "$TMP_FILE"; then
  echo "Failed to rewrite $STORY_FILE — left unchanged." >&2
  exit 1
fi

# Belt and suspenders on top of the pre-flight check above: awk exits 0
# whether or not its pattern actually matched anything, so this is what
# catches any other way the rewrite could silently no-op (a future edit to
# AWK_PROGRAM, a story whose Note row doesn't match the exact `| **Note** |`
# prefix) before the no-op is ever written back as if it were a success.
if ! grep -q "^| \*\*Zone\*\* | ${ZONE_TITLE} |\$" "$TMP_FILE"; then
  echo "Rewrite of $STORY_FILE did not produce the expected '| **Zone** | ${ZONE_TITLE} |' row — left unchanged." >&2
  exit 1
fi

if ! chmod "$ORIG_MODE" "$TMP_FILE"; then
  echo "Failed to set the file mode on the rewritten $STORY_FILE — left unchanged." >&2
  exit 1
fi

if ! mv "$TMP_FILE" "$STORY_FILE"; then
  echo "Failed to write $STORY_FILE — left unchanged." >&2
  exit 1
fi
CUR_TMP=""

echo "Zone: ${ZONE}"
