#!/bin/bash
# local-backlog — a local issue/story tracker for Claude Code, no cloud account needed
# Copyright (C) 2026  lbecjx
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version. See LICENSE for the full text.

# Reads which zone — backlog, planner, or archive — a story is in, directly
# from the story's own `| **Zone** |` row (LB-0014: the board file is gone,
# a story's zone is a fact about the story). The read-only counterpart to
# set-zone.sh; the update-status skill uses it to decide whether a story is
# already on the Planner board (and so doesn't need to be offered the move
# again).
#
# Usage: get-zone.sh <story-file>
# Prints one of: backlog | planner | archive (lowercase, same values
# VALID_ZONES in idle_server.py uses) — a missing row, or a value that
# isn't one of the canonical Title Case Zone values, defaults to `backlog`
# the same way a brand-new story (before create-story's template default
# is even written) would read.

STORY_FILE="$1"

if [[ -z "$STORY_FILE" ]]; then
  echo "Usage: get-zone.sh <story-file>" >&2
  exit 1
fi

if [[ ! -f "$STORY_FILE" ]]; then
  echo "No such file: $STORY_FILE" >&2
  exit 1
fi

# The value's case is normalized before the match. `update-status.sh`'s own
# archived-story guard normalizes case too (and `idle_server.py`'s does via
# `_is_archived`), so the three Zone readers agree: a `| **Zone** | archive |`
# row (any casing) means the same thing everywhere. The row SHAPE stays exact
# (same grep as update-status.sh) — a hand-edited `|**Zone**|` row is not a row
# any reader recognizes, so all three fail open to `backlog` together.
ZONE_VALUE=$(grep -m1 '^| \*\*Zone\*\* |' "$STORY_FILE" | sed -E 's/^\| \*\*Zone\*\* \| *//; s/ *\|$//' | tr '[:upper:]' '[:lower:]')

case "$ZONE_VALUE" in
  backlog) echo "backlog" ;;
  planner) echo "planner" ;;
  archive) echo "archive" ;;
  *) echo "backlog" ;;
esac
