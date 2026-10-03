#!/bin/bash
# local-backlog — a local issue/story tracker for Claude Code, no cloud account needed
# Copyright (C) 2026  lbecjx
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version. See LICENSE for the full text.

# Backfills every story's own `| **Zone** |` row from a legacy
# `.backlog-board.json` (LB-0014: zone membership lives on the story now,
# not a separate board file), then deletes that file once every write
# succeeds — the actual completion condition, not an optional cleanup.
#
# Dry run by default: prints which story would get which Zone value (and
# that the board file would then be deleted), touching nothing. --write
# applies it: writes each story's Zone via set-zone.sh, and deletes the
# board file only if every one of those writes succeeded. A code listed in
# the board with no matching story file (or more than one) is reported and
# left unmigrated, blocking the board file's deletion the same way a failed
# write would — never silently skipped.
#
# A code in neither list needs no write at all: a story's own Zone row
# already defaults to Backlog (create-story's template), so this script
# only ever writes the two non-default zones. A code in both lists (only
# possible on a hand-edited board) ends up Archive — the same precedence
# the old board readers used.
#
# Usage: migrate-zone-field.sh [--write] [backlog-dir]   (default: ./local-backlog)
# Exit 0 when there is nothing to migrate; non-zero only on a real error.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SET_ZONE_SCRIPT="$SCRIPT_DIR/../../update-status/scripts/set-zone.sh"

WRITE=0
DIR=""
for arg in "$@"; do
  case "$arg" in
    --write) WRITE=1 ;;
    *) DIR="$arg" ;;
  esac
done
DIR="${DIR:-local-backlog}"

if [[ ! -d "$DIR" ]]; then
  echo "No such directory: $DIR" >&2
  exit 1
fi

BOARD_FILE="$DIR/.backlog-board.json"
if [[ ! -f "$BOARD_FILE" ]]; then
  exit 0
fi

# Read-only parse, no lock needed (mirrors migrate-board-archive.sh's own
# dry-run read: writers publish through an atomic os.replace, so a reader
# always sees a whole board). The actual writes below go through
# set-zone.sh, which takes its own lock per story file. Archive is printed
# last so the bash loop below applies it last — the final Zone write for a
# code listed in both is the one that sticks.
PLAN=$(python3 - "$BOARD_FILE" <<'PYEOF'
import json
import re
import sys

board_file = sys.argv[1]
try:
    with open(board_file) as f:
        board = json.load(f)
except json.JSONDecodeError as e:
    print(f"{board_file} contains invalid JSON: {e}", file=sys.stderr)
    sys.exit(1)

if not isinstance(board, dict):
    print(f"{board_file} must contain a JSON object", file=sys.stderr)
    sys.exit(1)

# Same shape as CODE_PATTERN in idle_server.py / set-board.sh's own grep —
# a string that isn't a real code (stray glob metacharacters, a hand-edit
# typo) is unrecognized membership, same as a non-string entry, not passed
# through to the find/set-zone.sh step below.
CODE_RE = re.compile(r"^[A-Z]{2,6}-[0-9]{4}$")

planner = board.get("planner")
archive = board.get("archive")
planner = [c for c in planner if isinstance(c, str) and CODE_RE.match(c)] if isinstance(planner, list) else []
archive = [c for c in archive if isinstance(c, str) and CODE_RE.match(c)] if isinstance(archive, list) else []

for code in planner:
    print(f"{code}\tPlanner")
for code in archive:
    print(f"{code}\tArchive")
PYEOF
)
if [[ $? -ne 0 ]]; then
  exit 1
fi

if [[ -z "$PLAN" ]]; then
  # Nothing with a real (string) code to migrate — e.g. a board that only
  # ever held pre-LB-0012 garbage. Vacuously "every write succeeded," so
  # --write still retires the board file; a dry run prints nothing, same as
  # the normal case with nothing left to report.
  [[ "$WRITE" == "1" ]] && rm -f "$BOARD_FILE"
  exit 0
fi

FAILED=0
while IFS=$'\t' read -r CODE ZONE_TITLE; do
  [[ -z "$CODE" ]] && continue
  MATCHES=()
  while IFS= read -r -d '' match; do
    MATCHES+=("$match")
  done < <(find "$DIR" -maxdepth 1 -name "${CODE}-*.md" -print0 | sort -z)

  if [[ ${#MATCHES[@]} -eq 0 ]]; then
    echo "$BOARD_FILE: no story file found for $CODE — left unmigrated" >&2
    FAILED=1
    continue
  fi
  if [[ ${#MATCHES[@]} -gt 1 ]]; then
    echo "$BOARD_FILE: ${#MATCHES[@]} story files match $CODE — left unmigrated" >&2
    FAILED=1
    continue
  fi

  echo "${MATCHES[0]}: Zone -> ${ZONE_TITLE}"
  if [[ "$WRITE" == "1" ]]; then
    ZONE_LOWER=$(echo "$ZONE_TITLE" | tr '[:upper:]' '[:lower:]')
    if ! bash "$SET_ZONE_SCRIPT" "${MATCHES[0]}" "$ZONE_LOWER" > /dev/null; then
      echo "$BOARD_FILE: failed to write Zone for $CODE — left unmigrated" >&2
      FAILED=1
    fi
  fi
done <<< "$PLAN"

if [[ "$WRITE" == "1" ]]; then
  if [[ "$FAILED" == "1" ]]; then
    echo "$BOARD_FILE left in place — not every story migrated successfully." >&2
    exit 1
  fi
  rm -f "$BOARD_FILE"
  exit 0
fi

[[ "$FAILED" == "1" ]] && exit 1
exit 0
