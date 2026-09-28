#!/bin/bash
# local-backlog — a local issue/story tracker for Claude Code, no cloud account needed
# Copyright (C) 2026  lbecjx
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version. See LICENSE for the full text.

# Rewrites legacy archive entries in `.backlog-board.json` from the old
# `{ "code": <code> }` object to a bare code string, the canonical shape since
# LB-0012 (identical to `planner`). A board that has been written since then is
# already canonical — set-board.sh normalizes on every write — so this is for
# the one case that never gets written again: every story already archived.
#
# Runs as a dry run by default (prints the exact entries it would change and
# touches nothing); pass --write to apply the change atomically. Idempotent:
# once canonical, the dry run prints nothing and --write is a no-op.
#
# Usage: migrate-board-archive.sh [--write] [backlog-dir]   (default: ./local-backlog)
# Exit 0 when there is nothing to migrate; non-zero only on a real error.

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

python3 - "$BOARD_FILE" "$WRITE" <<'PYEOF'
import fcntl
import json
import os
import sys

board_file, write = sys.argv[1], sys.argv[2] == "1"

# A --write run rewrites the same file set-board.sh does, so it takes the same
# lock and stays serialized with a concurrent board write coming from the
# server (idle_server.py shells one out per request). A dry run only reads, so
# it takes no lock: writers publish through an atomic os.replace, so a reader
# always sees a whole board.
lock_fd = None
if write:
    lock_fd = open(board_file + ".lock", "a+")
    fcntl.flock(lock_fd, fcntl.LOCK_EX)

try:
    try:
        with open(board_file) as f:
            board = json.load(f)
    except json.JSONDecodeError as e:
        print(f"{board_file} contains invalid JSON: {e}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(board, dict):
        print(f"{board_file} must contain a JSON object", file=sys.stderr)
        sys.exit(1)

    archive = board.get("archive")
    if not isinstance(archive, list):
        sys.exit(0)

    # Only `{ "code": <code> }` objects are migrated to a bare code; a bare
    # string is already canonical, and anything else is left exactly as it is
    # — this script repairs a known shape, it does not silently drop data it
    # doesn't recognize.
    canonical = []
    changes = []
    for entry in archive:
        if isinstance(entry, dict) and isinstance(entry.get("code"), str):
            code = entry["code"]
            changes.append(code)
            canonical.append(code)
        else:
            canonical.append(entry)

    if not changes:
        sys.exit(0)

    for code in changes:
        print(f'{board_file}: {{"code": "{code}"}} -> "{code}"')

    if not write:
        sys.exit(0)

    board["archive"] = canonical
    # A temp name of its own, not set-board.sh's `.tmp`: holding the lock
    # already serializes the two, and this makes a collision impossible even
    # if some other writer ever forgot to take it.
    tmp_file = board_file + ".migrate.tmp"
    with open(tmp_file, "w") as f:
        json.dump(board, f, indent=2)
        f.write("\n")
    os.replace(tmp_file, board_file)
finally:
    if lock_fd is not None:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        lock_fd.close()
PYEOF
