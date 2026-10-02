#!/bin/bash
# local-backlog — a local issue/story tracker for Claude Code, no cloud account needed
# Copyright (C) 2026  lbecjx
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version. See LICENSE for the full text.

# Finds the story files that have no `## History` section — every story created
# before that section existed — and, with --write, adds one. update-status.sh
# refuses such a story outright (it has nowhere to log the transition), and its
# own remedy is "add one by hand"; this is the script that does it instead.
#
# The repair creates the section and says why it is there. It does not rebuild
# a log that was never kept: no `Status: <old> → <new>` line is invented, and
# the story's `Created` date is not touched. The one entry carries a real
# `date -u` stamp, so the history starts at the moment of the repair.
#
# A story that already has a `## History` heading is left alone, with or
# without entries — update-status.sh accepts both, so neither is broken.
#
# Runs as a dry run by default (prints one path per story it would repair and
# touches nothing); pass --write to apply. Idempotent: once every story has the
# section, the dry run prints nothing and --write is a no-op.
#
# Usage: repair-missing-history.sh [--write] [backlog-dir]   (default: ./local-backlog)
# Exit 0 when nothing failed; non-zero on a bad directory or a story that could
# not be repaired (that story is left unchanged).

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

# Same line update-status.sh's guard greps for, so this agrees with the refusal
# it exists to answer.
has_history() {
  grep -q '^## History$' "$1"
}

repair_file() {
  local file="$1"
  local lock_dir="${file}.lock"
  local wait=0

  # mkdir is atomic on any POSIX filesystem — the same portable mutex
  # update-status.sh takes, so a repair can't interleave with a status change
  # on the same story.
  until mkdir "$lock_dir" 2>/dev/null; do
    sleep 0.05
    wait=$((wait + 1))
    if [[ "$wait" -ge 200 ]]; then
      echo "Could not acquire lock on $file after 10s — another update may be stuck" >&2
      return 1
    fi
  done

  # Re-checked under the lock: a concurrent writer may have added the section
  # between the scan and here.
  if has_history "$file"; then
    rmdir "$lock_dir" 2>/dev/null
    return 0
  fi

  local now tmp
  now=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  tmp=$(mktemp) || { rmdir "$lock_dir" 2>/dev/null; return 1; }
  # mktemp creates the file 0600, and mv would carry that onto the story.
  # Copying the original first keeps its mode; the redirect below only
  # truncates and refills it.
  if ! cp -p "$file" "$tmp"; then
    rm -f "$tmp"
    rmdir "$lock_dir" 2>/dev/null
    echo "Failed to prepare a copy of $file — left unchanged." >&2
    return 1
  fi

  # The entry goes through the environment, not awk -v, which would run it
  # through awk's escape processing. The file is held in memory because the
  # insertion point (the closing `---` just above the footer) is only known
  # once the whole file has been read.
  if ! HISTORY_ENTRY="- ${now} — History section added by /local-backlog:fix (story predates it)" awk '
    { line[NR] = $0 }
    /^> Generated with/ { footer = NR }
    END {
      at = 0
      if (footer) {
        # The closing `---` is the nearest non-blank line above the footer; any
        # other `---` (the one under the metadata table, a rule inside the
        # body) is not the end of the story and is never used.
        i = footer - 1
        while (i >= 1 && line[i] == "") i--
        at = (i >= 1 && line[i] == "---") ? i : footer
      }
      for (n = 1; n <= NR; n++) {
        if (n == at) emit_section(at > 1 && line[at - 1] != "")
        print line[n]
      }
      # No footer to anchor on: append at the end of the file.
      if (!at) emit_section(NR > 0 && line[NR] != "")
    }
    function emit_section(need_blank) {
      if (need_blank) print ""
      print "## History"
      print ""
      print ENVIRON["HISTORY_ENTRY"]
      print ""
    }
  ' "$file" > "$tmp"; then
    rm -f "$tmp"
    rmdir "$lock_dir" 2>/dev/null
    echo "Failed to rewrite $file — left unchanged." >&2
    return 1
  fi

  # Checked too, so an unwritable story is reported instead of looking repaired.
  if ! mv "$tmp" "$file"; then
    rm -f "$tmp"
    rmdir "$lock_dir" 2>/dev/null
    echo "Failed to write $file — left unchanged." >&2
    return 1
  fi

  rmdir "$lock_dir" 2>/dev/null
  return 0
}

STATUS=0

# Only files named like a story (`<PREFIX>-XXXX-*.md`) are considered — the same
# shape every other fix script keys on — so a stray `.md` in the folder is ignored.
for file in "$DIR"/*.md; do
  [[ -e "$file" ]] || continue
  base="$(basename "$file")"
  [[ "$base" =~ ^[A-Z]{2,6}-[0-9]{4}- ]] || continue

  has_history "$file" && continue

  if [[ "$WRITE" == "1" ]]; then
    repair_file "$file" || { STATUS=1; continue; }
  fi
  printf '%s\n' "$file"
done

exit "$STATUS"
