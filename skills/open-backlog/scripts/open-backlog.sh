#!/bin/bash
# local-backlog — a local issue/story tracker for Claude Code, no cloud account needed
# Copyright (C) 2026  lbecjx
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version. See LICENSE for the full text.

# Shipped as a real file (not inlined in SKILL.md) on purpose: a fixed,
# static command line ("bash <this-file>") is what lets Claude Code's
# permission system recognize the same command across runs, instead of
# re-prompting on every invocation for an inline script whose content is
# never byte-identical twice.

set -e

DIST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/dist"

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
if [ ! -d "$REPO_ROOT/backlog" ]; then
  echo "NO_BACKLOG"
  exit 0
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "NO_PYTHON3"
  exit 0
fi

HASH=$(printf '%s' "$REPO_ROOT" | shasum | cut -c1-12)
STAGE="${TMPDIR:-/tmp}/local-backlog-viewer/$HASH"
mkdir -p "$STAGE"
cp -R "$DIST_DIR/." "$STAGE/"
ln -sfn "$REPO_ROOT/backlog" "$STAGE/backlog"

PORT=""
if [ -f "$STAGE/.viewer.pid" ]; then
  PID=$(cut -d: -f1 "$STAGE/.viewer.pid")
  PORT=$(cut -d: -f2 "$STAGE/.viewer.pid")
  if ! kill -0 "$PID" 2>/dev/null; then
    PORT=""
  fi
fi
if [ -z "$PORT" ]; then
  PORT=8420
  TRIES=0
  while lsof -i :"$PORT" >/dev/null 2>&1; do
    PORT=$((PORT + 1))
    TRIES=$((TRIES + 1))
    if [ "$TRIES" -ge 20 ]; then
      echo "NO_FREE_PORT"
      exit 0
    fi
  done
  nohup python3 -m http.server "$PORT" --directory "$STAGE" >/dev/null 2>&1 &
  echo "$!:$PORT" > "$STAGE/.viewer.pid"
fi

open "http://localhost:$PORT/" 2>/dev/null || xdg-open "http://localhost:$PORT/" 2>/dev/null

echo "OPENED:$PORT"
echo "STORIES:$(ls "$REPO_ROOT"/backlog/*.md 2>/dev/null | wc -l | tr -d ' ')"
