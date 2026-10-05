#!/bin/bash
# local-backlog — a local issue/story tracker for Claude Code, no cloud account needed
# Copyright (C) 2026  lbecjx
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version. See LICENSE for the full text.

# SessionStart hook — lists the stories still Not Started, so a new session in
# a project that uses this plugin sees what is waiting without having to open
# the viewer. It is deliberately standalone: it reads only this plugin's own
# `local-backlog/` data (never another plugin's, and never references one in
# its output) and never writes anything.
#
# Claude Code `SessionStart`, JSON on stdin, JSON envelope on stdout:
#   {"source":"startup"} ->
#   {"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"…"}}
# Silence (exit 0, no output) in every other case: a non-startup session, a
# project with no marker, or a backlog with nothing Not Started.

set -u

# Two modes, one text (mirrors workflow-dev's session-start-check.sh):
#   session-start-list.sh              Claude Code SessionStart — reads the
#                                      payload on stdin, emits the JSON envelope.
#   session-start-list.sh --message [payload]
#                                      prints the same text plain, and nothing
#                                      otherwise. OpenCode's plugin
#                                      (opencode/plugin.ts) calls this; that
#                                      harness has no SessionStart event, so the
#                                      plugin passes the payload as an argument
#                                      and owns the "once per session" half.
MODE="hook"
PAYLOAD_ARG=""
case "${1:-}" in
  --message) MODE="message"; PAYLOAD_ARG="${2:-}" ;;
esac

if [[ "$MODE" == "message" && -n "$PAYLOAD_ARG" ]]; then
  INPUT="$PAYLOAD_ARG"
else
  INPUT=$(cat)
fi

# --- Session gate -------------------------------------------------------------
# Act only on a genuinely new session: `source` is "startup" for those and
# resume/clear/compact otherwise, so the list is not repeated mid-conversation.
# The field is `source`, not `session_start_reason` — the wrong name never
# matches Claude Code's actual input and makes the whole hook a silent no-op.
SOURCE=$(printf '%s' "$INPUT" | grep -o '"source"[[:space:]]*:[[:space:]]*"[^"]*"' | cut -d'"' -f4)
[[ "$SOURCE" == "startup" ]] || exit 0

# --- Marker gate --------------------------------------------------------------
# Only projects that actually use this plugin, per ECOSYSTEM.md's markers table.
[[ -f "local-backlog/.backlog-config.json" ]] || exit 0

# --- Reuse the zone reader the update-status skill owns -----------------------
# get-zone.sh prints backlog|planner|archive and owns the missing/unknown->
# backlog rule; resolve it from this script's own location so it works no
# matter what the caller's cwd or CLAUDE_PLUGIN_ROOT is.
SCRIPT_DIR=$(cd -P "$(dirname "$0")" && pwd -P)
GET_ZONE="$SCRIPT_DIR/../skills/update-status/scripts/get-zone.sh"

# A metadata row's value: `| **Label** | value |` -> value. CR is stripped here
# so a CRLF story still parses — otherwise its Code row keeps a trailing `\r`,
# the shape check below rejects it, and the whole story is silently skipped.
row_value() {
  grep -m1 "^| \*\*$1\*\* |" "$2" | tr -d '\r' | sed -E "s/^\| \*\*$1\*\* \| *//; s/ *\|$//"
}

CAP=10

# Collect candidates as "priority_rank<TAB>code<TAB>title<TAB>priority".
ROWS=""
for FILE in local-backlog/*.md; do
  [[ -f "$FILE" ]] || continue

  CODE=$(row_value Code "$FILE")
  # A story whose Code row is missing or malformed is skipped, never fatal; the
  # shape check also keeps CODE safe to use in the title-strip pattern below.
  printf '%s' "$CODE" | grep -qE '^[A-Z]{2,6}-[0-9]{4}$' || continue

  STATUS=$(row_value Status "$FILE")
  [[ "$STATUS" == "Not Started" ]] || continue

  ZONE=$(bash "$GET_ZONE" "$FILE" 2>/dev/null)
  # get-zone.sh prints exactly these three values; anything else (a missing or
  # broken install) means we cannot tell the zone, so skip the story rather than
  # risk listing one that is really in Archive.
  case "$ZONE" in
    backlog|planner|archive) ;;
    *) continue ;;
  esac
  [[ "$ZONE" == "archive" ]] && continue

  PRIORITY=$(row_value Priority "$FILE")
  # A tab would collide with the row delimiter (and a pipe with the Markdown
  # table); quotes/backslashes would break the JSON envelope.
  PRIORITY=$(printf '%s' "$PRIORITY" | tr '\t' ' ' | tr -d '"\\' | tr '|' '/')
  [[ -n "$PRIORITY" ]] || PRIORITY="-"

  TITLE=$(head -1 "$FILE" | sed -E 's/^#+[[:space:]]*//')
  TITLE=$(printf '%s' "$TITLE" | sed -E "s/^${CODE}[[:space:]]*(·|:|-)?[[:space:]]*//")
  TITLE=$(printf '%s' "$TITLE" | tr '\t' ' ' | tr -d '\r"\\' | tr '|' '/')

  case "$PRIORITY" in
    High) RANK=0 ;;
    Medium) RANK=1 ;;
    Low) RANK=2 ;;
    *) RANK=3 ;;
  esac

  ROWS="${ROWS}${RANK}	${CODE}	${TITLE}	${PRIORITY}
"
done

TOTAL=$(printf '%s' "$ROWS" | grep -c .)
[[ "$TOTAL" -gt 0 ]] || exit 0

SHOWN=$(printf '%s' "$ROWS" | LC_ALL=C sort -t"$(printf '\t')" -k1,1n -k2,2 | head -n "$CAP")
BODY=$(printf '%s\n' "$SHOWN" | awk -F'\t' '{ printf "| %s | %s | %s |\n", $2, $3, $4 }')

TEXT="local-backlog — stories not started:

| Code | Title | Priority |
|---|---|---|
${BODY}"

if (( TOTAL > CAP )); then
  TEXT="${TEXT}
(+$((TOTAL - CAP)) more — run /local-backlog:open-backlog)"
fi

# The JSON envelope below cannot carry a raw `"` or `\`, nor any control
# character (a `\r` that reached a field, say) — JSON must escape all of those.
# Fields are cleaned on the way in; this is the final guarantee, so a malformed
# row can never emit invalid JSON. Tab (011) and newline (012) are kept: the
# newline pass below handles the latter and nothing else carries the former.
TEXT=$(printf '%s' "$TEXT" | tr -d '"\\' | LC_ALL=C tr -d '\000-\010\013-\037')

# One copy of the text, two envelopes: `--message` prints it plain for
# OpenCode's plugin, hook mode wraps it for Claude Code. JSON cannot carry a
# raw newline, so each one becomes `\n`; the text holds no `"` or `\` to escape.
if [[ "$MODE" == "message" ]]; then
  printf '%s' "$TEXT"
else
  printf '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"%s"}}' \
    "$(printf '%s' "$TEXT" | awk 'NR > 1 { printf "\\n" } { printf "%s", $0 }')"
fi
