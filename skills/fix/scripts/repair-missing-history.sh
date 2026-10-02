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
# touches nothing); pass --write to apply, which prints each path it repaired.
# A symlink in the folder is skipped with a message, never rewritten. Idempotent: once every story has the
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

# The lock and the temp file currently held. One cleanup releases both on every
# return path and on INT/TERM, so a normal failure or a Ctrl-C does not leave a
# `<story>.lock` behind: that directory would make update-status.sh wait out its
# 10s timeout on the story until someone removed it by hand. (A signal landing in
# the instant between `mkdir`/`mktemp` and recording it below can still leak one.)
CUR_LOCK=""
CUR_TMP=""
release() {
  [[ -n "$CUR_TMP" ]] && rm -f "$CUR_TMP"
  [[ -n "$CUR_LOCK" ]] && rmdir "$CUR_LOCK" 2>/dev/null
  CUR_TMP=""
  CUR_LOCK=""
}
trap release EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# Runs with the lock held. Writes the repaired copy next to the story, so the
# final `mv` is a same-filesystem rename — atomic — rather than a copy.
rewrite_story() {
  local file="$1"

  # Re-checked under the lock: a concurrent writer may have added the section
  # between the scan and here.
  if has_history "$file"; then
    return 0
  fi

  local now
  now=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  if ! CUR_TMP=$(mktemp "${file}.XXXXXX"); then
    CUR_TMP=""
    echo "Failed to create a temp file next to $file — left unchanged." >&2
    return 1
  fi
  # mktemp creates the file 0600, and mv would carry that onto the story.
  # Copying the original first keeps its mode; the redirect below only
  # truncates and refills it.
  if ! cp -p "$file" "$CUR_TMP"; then
    echo "Failed to prepare a copy of $file — left unchanged." >&2
    return 1
  fi

  # The entry goes through the environment, not awk -v, which would run it
  # through awk's escape processing. The file is held in memory because the
  # insertion point (the closing `---` just above the footer) is only known
  # once the whole file has been read. Comparisons ignore a trailing \r so a
  # CRLF story is anchored the same way as an LF one.
  if ! HISTORY_ENTRY="- ${now} — History section added by /local-backlog:fix (story predates it)" awk '
    function bare(s) { sub(/\r$/, "", s); return s }
    function emit_section(need_blank) {
      if (need_blank) print ""
      print "## History"
      print ""
      print ENVIRON["HISTORY_ENTRY"]
      print ""
    }
    { line[NR] = $0 }
    /^> Generated with/ { footer = NR }
    END {
      at = 0
      if (footer) {
        # The closing `---` is the nearest non-blank line above the footer; any
        # other `---` (the one under the metadata table, a rule inside the
        # body) is not the end of the story and is never used.
        i = footer - 1
        while (i >= 1 && bare(line[i]) == "") i--
        at = (i >= 1 && bare(line[i]) == "---") ? i : footer
      }
      for (n = 1; n <= NR; n++) {
        if (n == at) emit_section(at > 1 && bare(line[at - 1]) != "")
        print line[n]
      }
      # No footer to anchor on: append at the end of the file.
      if (!at) emit_section(NR > 0 && bare(line[NR]) != "")
    }
  ' "$file" > "$CUR_TMP"; then
    echo "Failed to rewrite $file — left unchanged." >&2
    return 1
  fi

  # Checked too, so an unwritable story is reported instead of looking repaired.
  if ! mv "$CUR_TMP" "$file"; then
    echo "Failed to write $file — left unchanged." >&2
    return 1
  fi
  CUR_TMP=""
  return 0
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
  CUR_LOCK="$lock_dir"

  rewrite_story "$file"
  local rc=$?
  release
  return "$rc"
}

STATUS=0

# Only files named like a story (`<PREFIX>-XXXX-*.md`) are considered — the same
# shape every other fix script keys on — so a stray `.md` in the folder is ignored.
for file in "$DIR"/*.md; do
  [[ -e "$file" ]] || continue
  base="$(basename "$file")"
  [[ "$base" =~ ^[A-Z]{2,6}-[0-9]{4}- ]] || continue

  # A rewrite replaces the file, so a symlink would be swapped for a regular
  # file holding its target's content — copying whatever it points at into the
  # backlog. Stories are plain files; leave a link for a human to look at.
  if [[ -L "$file" ]]; then
    echo "Skipping symlink: $file" >&2
    continue
  fi

  has_history "$file" && continue

  if [[ "$WRITE" == "1" ]]; then
    repair_file "$file" || { STATUS=1; continue; }
  fi
  printf '%s\n' "$file"
done

exit "$STATUS"
