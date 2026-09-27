#!/bin/bash
# local-backlog — a local issue/story tracker for Claude Code, no cloud account needed
# Copyright (C) 2026  lbecjx
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version. See LICENSE for the full text.

# Reads which "board" zone a story is in — planner, archive, or backlog —
# from backlog/.backlog-board.json. The read-only counterpart to set-board.sh
# (which writes the same file); the update-status skill uses it to decide
# whether a story is already on the Planner board (and so doesn't need to be
# offered the move again).
#
# Usage: get-board.sh <story-file>
# Prints one of: backlog | planner | archive. A story absent from both lists —
# including when the board file doesn't exist yet — is in the default `backlog`
# zone. Exit 1 (with a message on stderr) only if the file is unreadable or the
# board JSON is corrupt.

STORY_FILE="$1"

if [[ -z "$STORY_FILE" ]]; then
  echo "Usage: get-board.sh <story-file>" >&2
  exit 1
fi

if [[ ! -f "$STORY_FILE" ]]; then
  echo "No such file: $STORY_FILE" >&2
  exit 1
fi

# Same shape as set-board.sh's own extraction — keep both in sync by hand if
# the <PREFIX>-XXXX format ever changes.
CODE=$(basename "$STORY_FILE" | grep -oE '^[A-Z]{2,6}-[0-9]{4}')
if [[ -z "$CODE" ]]; then
  echo "Could not extract a <PREFIX>-XXXX code from filename: $(basename "$STORY_FILE")" >&2
  exit 1
fi

BOARD_FILE="$(dirname "$STORY_FILE")/.backlog-board.json"

# No board file means nothing has been placed yet — every story is in the
# default `backlog` zone. That's a normal state, not an error.
if [[ ! -f "$BOARD_FILE" ]]; then
  echo "backlog"
  exit 0
fi

# The JSON is nested (archive entries are objects), so python3 reads it — the
# same reason set-board.sh does. No lock: this only reads.
python3 - "$BOARD_FILE" "$CODE" <<'PYEOF'
import json
import sys

board_file, code = sys.argv[1:3]
try:
    with open(board_file) as f:
        board = json.load(f)
except json.JSONDecodeError as e:
    print(f"{board_file} contains invalid JSON: {e}", file=sys.stderr)
    sys.exit(1)

if not isinstance(board, dict):
    print(f"{board_file} must contain a JSON object", file=sys.stderr)
    sys.exit(1)

planner = board.get("planner")
archive = board.get("archive")
planner = planner if isinstance(planner, list) else []
archive = archive if isinstance(archive, list) else []

# Archive is checked first: if a code somehow appears in both lists, archive
# wins — the same precedence the viewer resolves with, and the same invariant
# set-board.sh maintains (it strips a code from both lists before re-adding it,
# so overlap can only come from an externally-edited board).
if any(isinstance(entry, dict) and entry.get("code") == code for entry in archive):
    zone = "archive"
elif code in planner:
    zone = "planner"
else:
    zone = "backlog"

print(zone)
PYEOF
