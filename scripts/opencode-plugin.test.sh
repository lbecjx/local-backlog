#!/bin/bash
# local-backlog — a local issue/story tracker for Claude Code, no cloud account needed
# Copyright (C) 2026  lbecjx
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version. See LICENSE for the full text.
#
# Tests for opencode/plugin.ts. OpenCode loads that file on Bun; its logic is
# plain JS, so it runs here under node against the real check script, with a
# stub plugin context that records what the plugin would have delivered.
#
# The stub mimics the surfaces this plugin uses (see workflow-dev's
# opencode/plugin.ts for the measurements): `session.hook("context")` with a
# **mutable** `messages` array. Real OpenCode is still the only thing that can
# load the plugin, fire a real session and render a notice — this covers
# everything after the hook fires: which script the plugin asks and where the
# answer goes.
#
#   bash scripts/opencode-plugin.test.sh
#
# Skips (exit 0) when node isn't available, since the plugin's own runtime is
# OpenCode's Bun and a missing node shouldn't read as a failure.

set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
PLUGIN="$HERE/../opencode/plugin.ts"

if ! command -v node >/dev/null 2>&1; then
  echo "  skip  node isn't installed — plugin.ts logic not exercised"
  exit 0
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
PROJECT="$TMP/project"
PLAIN="$TMP/plain"
EMPTY="$TMP/empty"
FAKE="$TMP/fake"

mkdir -p "$PROJECT/local-backlog" "$PLAIN" "$EMPTY/local-backlog" "$FAKE/opencode" "$FAKE/scripts"
printf '{"prefix":"QA","lastCode":1,"gitignored":true}' > "$PROJECT/local-backlog/.backlog-config.json"
cat > "$PROJECT/local-backlog/QA-0001-alpha.md" <<'STORY'
# QA-0001 · alpha story

| **Code** | QA-0001 |
| **Priority** | High |
| **Status** | Not Started |
| **Zone** | Backlog |
STORY

# A local-backlog project with the marker but nothing Not Started — the
# "clean empty" path that must stay silent without being retried forever.
printf '{"prefix":"QA","lastCode":2,"gitignored":true}' > "$EMPTY/local-backlog/.backlog-config.json"
cat > "$EMPTY/local-backlog/QA-0002-beta.md" <<'STORY'
# QA-0002 · beta story

| **Code** | QA-0002 |
| **Priority** | Low |
| **Status** | Done |
| **Zone** | Archive |
STORY

# A copy of the plugin whose sibling script fails on its first call and
# succeeds after — the transient-failure case. A failure must NOT mark the
# session as done, or one timeout would silence the list for the whole session.
cp "$PLUGIN" "$FAKE/opencode/plugin.ts"
cat > "$FAKE/scripts/session-start-list.sh" <<'FAKE'
#!/bin/bash
n=0
[ -f "$FAKE_STATE" ] && n=$(cat "$FAKE_STATE")
n=$((n + 1))
printf '%s' "$n" > "$FAKE_STATE"
[ "$n" -le 1 ] && exit 1
printf 'local-backlog — stories not started:\n\n| Code | Title | Priority |\n|---|---|---|\n| QA-0001 | alpha story | High |'
FAKE

cat > "$TMP/harness.ts" <<'HARNESS'
import { pathToFileURL } from "node:url"

const PLUGIN = process.env.PLUGIN_PATH!
const FAKE_PLUGIN = process.env.FAKE_PLUGIN!
const PROJECT = process.env.PROJECT!
const PLAIN = process.env.PLAIN!
const EMPTY = process.env.EMPTY!

let pass = 0
let fail = 0
const check = (label: string, condition: boolean) => {
  if (condition) { console.log("  ok   " + label); pass++ }
  else { console.log("  FAIL " + label); fail++ }
}

const newEvent = (sessionID: string) => ({ sessionID, system: [], messages: [] as any[] })
const injected = (event: any): string =>
  (event.messages ?? []).map((m: any) => m.content?.[0]?.text ?? "").join("\n")

const stubCtx = (directory: string) => {
  let contextHook: ((event: any) => Promise<void>) | undefined
  const ctx: any = {
    location: { directory },
    session: {
      hook: async (name: string, callback: (event: any) => Promise<void>) => {
        if (name === "context") contextHook = callback
        return { dispose: async () => {} }
      },
    },
  }
  return { ctx, fire: (event: any) => contextHook!(event), has: () => typeof contextHook === "function" }
}

const plugin = (await import(PLUGIN)).default
const main = stubCtx(PROJECT)
await plugin.setup(main.ctx)
check("setup registers session.hook('context')", main.has())

let ev = newEvent("ses_a")
await main.fire(ev)
check("a local-backlog project → the list is injected", injected(ev).includes("QA-0001"))
check("the injected text is labelled local-backlog", injected(ev).includes("[local-backlog]"))
check("the injected text is the plain list, not the JSON envelope",
  !injected(ev).includes("hookSpecificOutput"))

const first = injected(ev)
ev = newEvent("ses_a")
await main.fire(ev)
check("the same session is not listed twice", injected(ev) === "")

ev = newEvent("ses_b")
await main.fire(ev)
check("a different session gets its own list", injected(ev) === first)

ev = newEvent("ses_c")
const parts = ev.messages as any[]
await main.fire(ev)
check("the injected message uses the part-array shape",
  Array.isArray(parts?.[0]?.content) && parts[0].content[0]?.type === "text")

main.ctx.location.directory = PLAIN
ev = newEvent("ses_plain")
await main.fire(ev)
check("a project without the marker → nothing injected", injected(ev) === "")

main.ctx.location.directory = EMPTY
ev = newEvent("ses_empty")
await main.fire(ev)
check("a project with the marker but nothing Not Started → nothing injected", injected(ev) === "")

// The project directory also comes through `location.project.directory` when
// the top-level `directory` is absent.
main.ctx.location = { project: { directory: PROJECT } }
ev = newEvent("ses_fallback")
await main.fire(ev)
check("location.project.directory is used when directory is absent",
  injected(ev).includes("QA-0001"))

// The transient-failure regression: the copied plugin's script fails on the
// first call. That first call must deliver nothing AND leave the session
// unmarked, so the same session's next call retries and delivers.
const fake = (await import(pathToFileURL(FAKE_PLUGIN).href + "?fake")).default
const fctx = stubCtx(PROJECT)
await fake.setup(fctx.ctx)
const failEv = newEvent("ses_fail")
await fctx.fire(failEv)
check("a script that fails on the first call → nothing injected", injected(failEv) === "")
const retryEv = newEvent("ses_fail")
await fctx.fire(retryEv)
check("...and the same session retries instead of staying silent forever",
  injected(retryEv).includes("QA-0001"))

console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail === 0 ? 0 : 1)
HARNESS

PLUGIN_PATH="$PLUGIN" FAKE_PLUGIN="$FAKE/opencode/plugin.ts" \
  PROJECT="$PROJECT" PLAIN="$PLAIN" EMPTY="$EMPTY" FAKE_STATE="$TMP/fake-calls" \
  node "$TMP/harness.ts"
