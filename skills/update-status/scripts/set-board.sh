#!/bin/bash
# local-backlog — a local issue/story tracker for Claude Code, no cloud account needed
# Copyright (C) 2026  lbecjx
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version. See LICENSE for the full text.

# Updates which "board" a story belongs to — backlog, planner, or archive —
# tracked in a separate file, backlog/.backlog-board.json, since board
# membership is UI-organization state, not part of a story's own Status.
# Absence from both the planner and archive lists means "backlog" (the
# default); there is no explicit "backlog" list. A code is never listed in
# more than one zone after a single write: setting archive removes it from
# planner in the same pass, and setting planner or backlog removes it from
# archive — a single write can't leave the file in an inconsistent state.
#
# An archive entry is a bare code string, exactly like `planner`: the board
# only records which zone a code sits in. A story's Resolution and free-text
# Note belong to the story file itself (written by update-status.sh on the
# Done transition), not to the board.
#
# Older boards still hold archive entries as `{ "code": <code> }` objects —
# that object used to carry the resolution and reason. This script reads both
# shapes and rewrites every entry as a bare code in the same pass, so any
# board it touches comes out canonical with no separate migration step (see
# LB-0012).
#
# python3 does the read-modify-write for the fcntl lock and the atomic
# os.replace below (bash can't do either portably), not because the JSON is
# nested. python3 is already a hard dependency of this plugin (idle_server.py
# requires it), not a new one.
#
# Usage: set-board.sh <story-file> <backlog|planner|archive>
# Prints the resulting zone.

STORY_FILE="$1"
ZONE="$2"
shift 2 2>/dev/null

if [[ -z "$STORY_FILE" || -z "$ZONE" ]]; then
  echo "Usage: set-board.sh <story-file> <backlog|planner|archive>" >&2
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

# Zone values are duplicated as literals in
# open-backlog/scripts/idle_server.py (where they're validated a second
# time, before this script is ever invoked) — no shared source of truth
# across Python and bash, so keep both lists in sync by hand if either
# ever changes.
if [[ "$ZONE" != "backlog" && "$ZONE" != "planner" && "$ZONE" != "archive" ]]; then
  echo "'$ZONE' is not a valid zone — must be one of: backlog, planner, archive" >&2
  exit 1
fi

# Same shape as CODE_PATTERN in open-backlog/scripts/idle_server.py — keep
# both in sync by hand if the <PREFIX>-XXXX format ever changes.
CODE=$(basename "$STORY_FILE" | grep -oE '^[A-Z]{2,6}-[0-9]{4}')
if [[ -z "$CODE" ]]; then
  echo "Could not extract a <PREFIX>-XXXX code from filename: $(basename "$STORY_FILE")" >&2
  exit 1
fi

BOARD_FILE="$(dirname "$STORY_FILE")/.backlog-board.json"

# The read-modify-write below is locked (fcntl.flock, held for the whole
# critical section) because idle_server.py can run several of these
# concurrently — one subprocess per HTTP request, from a ThreadingTCPServer.
# Without a lock, two near-simultaneous calls each read the same pre-write
# board.json and one silently clobbers the other's change on write. `flock`
# the CLI tool doesn't ship on macOS, but Python's fcntl module does (POSIX,
# no new dependency), so the lock lives inside this same python3 process
# rather than wrapping it externally. The temp file is created next to
# BOARD_FILE (not the system temp dir) so the final rename is guaranteed to
# be on the same filesystem, and therefore atomic.
if python3 - "$BOARD_FILE" "$CODE" "$ZONE" <<'PYEOF'
import fcntl
import json
import os
import sys

board_file, code, zone = sys.argv[1:4]

lock_fd = open(board_file + ".lock", "a+")
fcntl.flock(lock_fd, fcntl.LOCK_EX)
try:
    if os.path.exists(board_file):
        with open(board_file) as f:
            try:
                board = json.load(f)
            except json.JSONDecodeError as e:
                print(f"{board_file} contains invalid JSON: {e}", file=sys.stderr)
                sys.exit(1)
    else:
        board = {}

    # Valid JSON that isn't an object (a list, a string, a number) reaches
    # `setdefault` below as an AttributeError otherwise, and idle_server relays
    # the traceback to the client. Fail the same clean way get-board.sh does.
    if not isinstance(board, dict):
        print(f"{board_file} must contain a JSON object", file=sys.stderr)
        sys.exit(1)

    board.setdefault("planner", [])
    board.setdefault("archive", [])

    # A hand-edited board can hold a non-list (a string, an object) where a
    # list belongs; treating it as an empty list keeps the list comprehensions
    # below from iterating its characters/keys into a bogus membership.
    board["planner"] = board["planner"] if isinstance(board["planner"], list) else []
    board["archive"] = board["archive"] if isinstance(board["archive"], list) else []

    # Normalize archive entries to bare codes in the same pass — this is what
    # migrates a board written before LB-0012 (entries as { "code": … }) into
    # the canonical shape, so the file is clean after any board write. Only a
    # `{ "code": <string> }` object is converted; anything else is left exactly
    # as it is — the readers treat a non-string as non-membership anyway, so
    # this repairs the known shape rather than dropping data it doesn't
    # recognize (the same policy as the fix skill's migration script).
    def archive_code(entry):
        if isinstance(entry, dict) and isinstance(entry.get("code"), str):
            return entry["code"]
        return entry

    board["archive"] = [archive_code(e) for e in board["archive"]]

    # Strip the code from both lists first, then re-add it to whichever
    # zone this call actually asked for — this is what guarantees a code
    # is never in more than one list after any single write.
    board["planner"] = [c for c in board["planner"] if c != code]
    board["archive"] = [c for c in board["archive"] if c != code]

    if zone == "planner":
        board["planner"].append(code)
    elif zone == "archive":
        board["archive"].append(code)
    # zone == "backlog": already removed from both lists above, nothing to add

    tmp_file = board_file + ".tmp"
    with open(tmp_file, "w") as f:
        json.dump(board, f, indent=2)
        f.write("\n")
    os.replace(tmp_file, board_file)
finally:
    fcntl.flock(lock_fd, fcntl.LOCK_UN)
    lock_fd.close()
PYEOF
then
  echo "Zone: ${ZONE}"
else
  echo "Failed to update $BOARD_FILE — left unchanged." >&2
  exit 1
fi
