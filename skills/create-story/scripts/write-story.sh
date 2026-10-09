#!/bin/bash
# local-backlog — a local issue/story tracker for Claude Code, no cloud account needed
# Copyright (C) 2026  lbecjx
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version. See LICENSE for the full text.

# Writes one or more new story files and assigns their codes at write time, so
# two sessions creating stories in the same project can never hand out the same
# code. The code an agent shows in a draft is read minutes earlier, while the
# story is still being discussed; another session can take it in the meantime.
# So the codes are decided here, inside a lock, from a fresh read:
#
#   1. re-read `prefix` and `lastCode` from <backlog-dir>/.backlog-config.json;
#   2. plan one code per draft: the next numbers after `lastCode` that have no
#      `<PREFIX>-XXXX-*.md` (or `<PREFIX>-XXXX.md`) file yet;
#   3. in each draft, replace `{{CODE}}` with the story's own code and
#      `{{CODE:<n>}}` with the code of the n-th story of this call, then create
#      the file exclusively — an existing file is never overwritten;
#   4. save `lastCode` as max(the value on disk now, the last code assigned),
#      so the counter never moves back.
#
# The counter stays the source of truth: the file check only skips numbers that
# are taken, it never derives the next code from the listing (that would reuse
# the code of a deleted story).
#
# Usage: write-story.sh <backlog-dir> <slug> <draft-file> [<slug> <draft-file> ...]
# Several pairs are a batch: one lock, one read, consecutive free codes in the
# order given, one counter write at the end. A batch is all or nothing: if any
# story cannot be written, the ones this run already wrote are removed.
# Prints, in order: `SKIPPED: <CODE> (taken by <file>)` for each number passed
# over, `CREATED: <CODE> <path>` for each story written, then `LASTCODE: <n>`.
# Exit 2 = a bad argument, exit 1 = any other failure; both write nothing.
# Exit 3 = the stories were written but the counter could not be saved (the
# next run skips their codes, so nothing is reused).

LOCK_POLL=0.05       # seconds between attempts
LOCK_MAX_TRIES=200   # 200 × 0.05s — the 10s the timeout message states
PLACEHOLDER='{{CODE}}'
MAX_LAST_CODE=999999999  # far beyond any backlog, well inside bash's integers

usage() {
  echo "Usage: write-story.sh <backlog-dir> <slug> <draft-file> [<slug> <draft-file> ...]" >&2
  exit 2
}

[[ $# -ge 3 && $(( ($# - 1) % 2 )) -eq 0 ]] || usage

BACKLOG_DIR="$1"
shift
CONFIG="$BACKLOG_DIR/.backlog-config.json"
STORY_COUNT=$(( $# / 2 ))

if [[ ! -d "$BACKLOG_DIR" ]]; then
  echo "No such backlog folder: $BACKLOG_DIR" >&2
  exit 2
fi

SLUGS=()
DRAFTS=()
while [[ $# -gt 0 ]]; do
  slug="$1"
  draft="$2"
  shift 2
  # The slug ends up in a filename: kebab-case ASCII only, so no `/`, no `..`,
  # no accents (see the workflow's file-name rule).
  if [[ ! "$slug" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ || ${#slug} -gt 80 ]]; then
    echo "Invalid slug '$slug': use lowercase kebab-case (a-z, 0-9, '-'), at most 80 characters." >&2
    exit 2
  fi
  if [[ ! -f "$draft" || ! -r "$draft" ]]; then
    echo "Draft file not found or not readable: $draft" >&2
    exit 2
  fi
  # Without the placeholder the draft carries a literal code written before the
  # final one was known, and it would go stale the moment the code moves.
  if ! LC_ALL=C grep -qF -- "$PLACEHOLDER" "$draft"; then
    echo "Draft $draft has no $PLACEHOLDER placeholder — write the code as $PLACEHOLDER so the final one can be filled in." >&2
    exit 2
  fi
  # A sibling reference must name a story of this call, or it would be left in
  # the file unreplaced.
  while IFS= read -r ref; do
    [[ -n "$ref" ]] || continue
    n="${ref#\{\{CODE:}"
    n="${n%\}\}}"
    if [[ ! "$n" =~ ^[1-9][0-9]{0,3}$ ]] || (( n > STORY_COUNT )); then
      echo "Draft $draft refers to $ref, but this call writes $STORY_COUNT story(ies): use {{CODE:1}} to {{CODE:$STORY_COUNT}}." >&2
      exit 2
    fi
  done <<< "$(LC_ALL=C grep -o '{{CODE:[^}]*}}' "$draft")"
  SLUGS+=("$slug")
  DRAFTS+=("$draft")
done

if [[ ! -f "$CONFIG" ]]; then
  echo "No $CONFIG — set the backlog up first (create-story Phase 1)." >&2
  exit 1
fi

# Reads `lastCode` from the given config text. Refuses a value bash arithmetic
# could not hold, rather than letting it wrap and move the counter back.
last_code_of() {
  local raw
  raw=$(printf '%s\n' "$1" | grep -o '"lastCode"[[:space:]]*:[[:space:]]*[0-9][0-9]*' | head -1 | grep -o '[0-9][0-9]*$')
  [[ -n "$raw" ]] || return 1
  raw=$(printf '%s' "$raw" | sed -E 's/^0+([0-9])/\1/')
  [[ ${#raw} -le ${#MAX_LAST_CODE} ]] || return 1
  # 10# so a value written with leading zeros isn't read as octal.
  echo $(( 10#$raw ))
}

# `mkdir` is atomic on any POSIX filesystem: a portable mutex with no `flock`
# CLI (absent on macOS). It serializes this script against itself; the
# exclusive create below still protects against a writer that takes no lock.
LOCK_DIR="$BACKLOG_DIR/.create-story.lock"
LOCK_WAIT=0
until mkdir "$LOCK_DIR" 2>/dev/null; do
  sleep "$LOCK_POLL"
  LOCK_WAIT=$((LOCK_WAIT + 1))
  if [[ "$LOCK_WAIT" -ge "$LOCK_MAX_TRIES" ]]; then
    echo "Could not acquire $LOCK_DIR after 10s — another story creation may be stuck; remove the folder if no other session is creating a story." >&2
    exit 1
  fi
done
# Installed after the lock is taken, so a run that timed out never removes
# another run's lock. Until every story of the call is written, an exit for any
# reason (a failure, INT, TERM) removes the stories this run created, so a batch
# is never left half written.
CUR_TMP=""
CREATED_FILES=()
WRITTEN=0
release() {
  local f
  [[ -n "$CUR_TMP" ]] && rm -f "$CUR_TMP"
  if [[ "$WRITTEN" -eq 0 ]]; then
    for f in "${CREATED_FILES[@]}"; do
      rm -f "$f"
    done
  fi
  rmdir "$LOCK_DIR" 2>/dev/null
}
trap release EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

CONFIG_TEXT=$(cat "$CONFIG")
PREFIX=$(printf '%s\n' "$CONFIG_TEXT" | grep -o '"prefix"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | sed -E 's/.*"([^"]*)"$/\1/')
if [[ ! "$PREFIX" =~ ^[A-Z]{2,5}$ ]]; then
  echo "$CONFIG has no valid \"prefix\" (2-5 uppercase letters) — fix the config first." >&2
  exit 1
fi
if ! LAST_CODE=$(last_code_of "$CONFIG_TEXT"); then
  echo "$CONFIG has no numeric \"lastCode\" of at most $MAX_LAST_CODE — fix the config first." >&2
  exit 1
fi

# The first file matching this code, if any. A dangling symlink counts as taken:
# creating over it would write wherever it points.
taken_by() {
  local f
  for f in "$BACKLOG_DIR/$1"-*.md "$BACKLOG_DIR/$1".md; do
    if [[ -e "$f" || -L "$f" ]]; then
      echo "$f"
      return 0
    fi
  done
  return 1
}

# Same placement rule as update-status.sh: next to the target (so `mv` is an
# atomic rename) only when that folder is private to this user; elsewhere a temp
# file could be swapped for a symlink before the write, so use $TMPDIR instead.
temp_template() {
  local dir
  dir=$(dirname "$1")
  if [[ -n "$(find "$dir" -maxdepth 0 -user "$(id -u)" ! -perm -020 ! -perm -002 2>/dev/null)" ]]; then
    echo "$1.XXXXXX"
  else
    echo "${TMPDIR:-/tmp}/$(basename "$1").XXXXXX"
  fi
}

# The rewrite and the max are computed from one read of the config, so a value
# read for the comparison is the same one the rewrite starts from.
save_counter() {
  local assigned="$1" text on_disk new mode
  text=$(cat "$CONFIG")
  if ! on_disk=$(last_code_of "$text"); then
    echo "$CONFIG lost its \"lastCode\" during the write — counter not saved; set it to at least $assigned." >&2
    return 1
  fi
  new=$(( on_disk > assigned ? on_disk : assigned ))
  if [[ "$new" -eq "$on_disk" ]]; then
    echo "LASTCODE: $new"
    return 0
  fi
  if ! CUR_TMP=$(mktemp "$(temp_template "$CONFIG")"); then
    CUR_TMP=""
    echo "Failed to create a temp file for $CONFIG — counter not saved; set \"lastCode\" to $new." >&2
    return 1
  fi
  mode=$(stat -c %a "$CONFIG" 2>/dev/null || stat -f %Lp "$CONFIG" 2>/dev/null)
  if ! printf '%s\n' "$text" | sed -E "s/(\"lastCode\"[[:space:]]*:[[:space:]]*)[0-9]+/\\1$new/" > "$CUR_TMP" \
      || ! grep -Eq "\"lastCode\"[[:space:]]*:[[:space:]]*$new([^0-9]|\$)" "$CUR_TMP" \
      || { [[ -n "$mode" ]] && ! chmod "$mode" "$CUR_TMP"; } \
      || ! mv "$CUR_TMP" "$CONFIG"; then
    echo "Failed to write $CONFIG — counter not saved; set \"lastCode\" to $new." >&2
    return 1
  fi
  CUR_TMP=""
  echo "LASTCODE: $new"
}

# Plan every code before writing anything, so a story can name a sibling's
# final code with {{CODE:<n>}}.
CODES=()
NEXT=$(( LAST_CODE + 1 ))
for i in "${!SLUGS[@]}"; do
  while :; do
    if (( NEXT > MAX_LAST_CODE )); then
      echo "No code left below $MAX_LAST_CODE." >&2
      exit 1
    fi
    CODE=$(printf '%s-%04d' "$PREFIX" "$NEXT")
    existing=$(taken_by "$CODE") || break
    echo "SKIPPED: $CODE (taken by $existing)"
    NEXT=$(( NEXT + 1 ))
  done
  CODES+=("$CODE")
  NEXT=$(( NEXT + 1 ))
done
LAST_ASSIGNED=$(( NEXT - 1 ))

SIBLING_EXPRS=()
for j in "${!CODES[@]}"; do
  SIBLING_EXPRS+=(-e "s/{{CODE:$(( j + 1 ))}}/${CODES[$j]}/g")
done

for i in "${!SLUGS[@]}"; do
  TARGET="$BACKLOG_DIR/${CODES[$i]}-${SLUGS[$i]}.md"
  # noclobber makes bash open with O_EXCL: the create fails if anything —
  # including a symlink — already sits at the path, instead of overwriting it.
  # The content is then written through that same descriptor, never by
  # reopening the path, so nothing swapped in after the create is followed.
  # Signals are ignored (not deferred) from the create until the file is on the
  # rollback list, so an interrupt can't land between them and strand it.
  trap '' INT TERM
  set -C
  if ! { exec 3> "$TARGET"; } 2>/dev/null; then
    set +C
    trap 'exit 130' INT
    trap 'exit 143' TERM
    if [[ -e "$TARGET" || -L "$TARGET" ]]; then
      echo "${CODES[$i]} was taken by a writer that bypassed the lock ($TARGET) — nothing written; run it again." >&2
    else
      echo "Failed to create $TARGET — nothing written." >&2
    fi
    exit 1
  fi
  set +C
  CREATED_FILES+=("$TARGET")
  trap 'exit 130' INT
  trap 'exit 143' TERM
  # LC_ALL=C: the placeholders are ASCII, and a byte-wise sed copies a draft in
  # any encoding instead of failing on bytes invalid in the current locale.
  if ! LC_ALL=C sed "${SIBLING_EXPRS[@]}" -e "s/$PLACEHOLDER/${CODES[$i]}/g" "${DRAFTS[$i]}" >&3; then
    exec 3>&-
    echo "Failed to write $TARGET — nothing written." >&2
    exit 1
  fi
  exec 3>&-
done
WRITTEN=1

for i in "${!CODES[@]}"; do
  echo "CREATED: ${CODES[$i]} ${CREATED_FILES[$i]}"
done
save_counter "$LAST_ASSIGNED" || exit 3
