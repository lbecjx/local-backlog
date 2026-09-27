#!/bin/bash
# local-backlog — a local issue/story tracker for Claude Code, no cloud account needed
# Copyright (C) 2026  lbecjx
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version. See LICENSE for the full text.

# Lists the story files whose Status is `Done` and whose Resolution is empty —
# the legacy gap left by every story that reached Done before the Resolution
# field existed. LB-0006 made `Status: Done ⇒ Resolution set` the invariant;
# this finds the stories that predate it, so `/local-backlog:fix` can offer to
# backfill them. Read-only: it prints one path per matching story and changes
# nothing.
#
# Usage: list-unresolved-done.sh [backlog-dir]   (default: ./local-backlog)
# Exit 0 whenever the directory exists; empty output means nothing to repair.

DIR="${1:-local-backlog}"

if [[ ! -d "$DIR" ]]; then
  echo "No such directory: $DIR" >&2
  exit 1
fi

# Only files named like a story (`<PREFIX>-XXXX-*.md`) are considered — the same
# shape every other script keys on — so a stray `.md` in the folder is ignored.
# The row value is stripped in two steps (`s///` then `s///`) so an empty
# `| **Resolution** |  |` reads as empty instead of as its raw line, which the
# single `(.*[^ ])` capture used elsewhere would leave behind.
for file in "$DIR"/*.md; do
  [[ -e "$file" ]] || continue
  base="$(basename "$file")"
  [[ "$base" =~ ^[A-Z]{2,6}-[0-9]{4}- ]] || continue

  status=$(grep -m1 '^| \*\*Status\*\* |' "$file" | sed -E 's/^\| \*\*Status\*\* \| *//; s/ *\|$//')
  [[ "$status" == "Done" ]] || continue

  resolution=$(grep -m1 '^| \*\*Resolution\*\* |' "$file" | sed -E 's/^\| \*\*Resolution\*\* \| *//; s/ *\|$//')
  if [[ -z "$resolution" ]]; then
    printf '%s\n' "$file"
  fi
done
