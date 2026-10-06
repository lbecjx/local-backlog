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
#
# The no-argument form above is that fixed command. Two additive shapes exist
# for the disambiguation flow (see SKILL.md): `--resolve-only` reports what
# would be opened without opening it, and `--root <path>` opens a specific
# project's backlog instead of resolving one from git/pwd.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIST_DIR="$(cd "$SCRIPT_DIR/.." && pwd)/dist"

RESOLVE_ONLY=0
ROOT_OVERRIDE=""
while [ $# -gt 0 ]; do
  case "$1" in
    --resolve-only)
      RESOLVE_ONLY=1
      shift
      ;;
    --root)
      if [ $# -lt 2 ] || [ -z "$2" ]; then
        echo "--root requires a non-empty path" >&2
        exit 2
      fi
      ROOT_OVERRIDE="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

if [ -n "$ROOT_OVERRIDE" ]; then
  # --root bypasses git/pwd resolution, but the same direct-child rule below
  # still applies to the path it names. Non-absolute operands are prefixed with
  # "./" so a leading-dash value can never be read as an option by `cd` — even
  # `cd -- -` still treats a bare `-` as $OLDPWD.
  case "$ROOT_OVERRIDE" in
    /*) REPO_ROOT="$(cd -- "$ROOT_OVERRIDE" 2>/dev/null && pwd)" || REPO_ROOT="" ;;
    *) REPO_ROOT="$(cd -- "./$ROOT_OVERRIDE" 2>/dev/null && pwd)" || REPO_ROOT="" ;;
  esac
else
  REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
fi
if [ -z "$REPO_ROOT" ] || [ ! -d "$REPO_ROOT/local-backlog" ]; then
  echo "NO_BACKLOG"
  exit 0
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "NO_PYTHON3"
  exit 0
fi

# Computed once and reused — the viewer header (project.json below) and the
# PROJECT: stdout line must never be two separate derivations of the same name.
PROJECT_NAME="$(basename "$REPO_ROOT")"
STORIES="$(ls "$REPO_ROOT"/local-backlog/*.md 2>/dev/null | wc -l | tr -d ' ')"

# --resolve-only reports what would be opened and exits — no staging, no
# server, no browser — so the caller can ask the human which project first.
if [ "$RESOLVE_ONLY" -eq 1 ]; then
  echo "PROJECT:$PROJECT_NAME"
  echo "ROOT:$REPO_ROOT"
  echo "STORIES:$STORIES"
  exit 0
fi

HASH=$(printf '%s' "$REPO_ROOT" | shasum | cut -c1-12)
STAGE="${TMPDIR:-/tmp}/local-backlog-viewer/$HASH"
mkdir -p "$STAGE"
cp -R "$DIST_DIR/." "$STAGE/"
# The staged symlink is named "local-backlog" — the path the bundled viewer
# fetches from (getBacklogBaseUrl() in backlog-viewer 0.6.0+ reads
# /local-backlog/). It also matches the project's own folder name. Naming it
# "backlog" left the viewer fetching a path that did not exist, so it showed
# "Failed to list http://localhost:<port>/local-backlog/: 404".
ln -sfn "$REPO_ROOT/local-backlog" "$STAGE/local-backlog"

# The authoritative data model (a story's fields + the canonical
# statuses/colors/resolutions) — the single source — served at the app's own
# root (not inside local-backlog/, which is per-project data) so the viewer's
# runtime fetch('/story-model.json') resolves to this exact file. Copied after
# dist/, deliberately overwriting any placeholder that ships inside
# backlog-viewer's own build output (used only for that project's isolated
# dev/test runs, never meant to reach a real project through this script).
cp "$SCRIPT_DIR/../../create-story/references/story-model.json" "$STAGE/story-model.json"

# The viewer's header shows this name so a human with several of these
# servers open (one per project, each on its own port) can tell tabs apart
# at a glance — see backlog-viewer's own project.json fetch. JSON-encoded via
# python3 (already required above) rather than hand-built, since a repo
# folder name can legally contain a `"` or `\`.
python3 -c 'import json, sys; json.dump({"name": sys.argv[1]}, sys.stdout)' "$PROJECT_NAME" > "$STAGE/project.json"

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
  nohup python3 "$SCRIPT_DIR/idle_server.py" "$PORT" "$STAGE" >/dev/null 2>&1 &
  echo "$!:$PORT" > "$STAGE/.viewer.pid"
fi

open "http://localhost:$PORT/" 2>/dev/null || xdg-open "http://localhost:$PORT/" 2>/dev/null

echo "OPENED:$PORT"
echo "STORIES:$STORIES"
echo "PROJECT:$PROJECT_NAME"
echo "ROOT:$REPO_ROOT"
