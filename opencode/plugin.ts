// local-backlog — a local issue/story tracker for Claude Code, no cloud account needed
// Copyright (C) 2026  lbecjx
//
// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version. See LICENSE for the full text.
//
// OpenCode side of the SessionStart story list.
//
// Claude Code gets this from `hooks/hooks.json`; OpenCode has no such file, so
// the same script is called from here instead. Nothing is reimplemented: the
// script owns both the wording and the "is this warranted?" test, and this file
// only decides *when* to ask it and *where* the answer goes. That is why there
// is no list text here at all — a second copy would be free to drift from the
// one Claude Code emits.
//
// OpenCode 2's plugin API is `export default { id, setup }`, and the context
// hook (`ctx.session.hook("context", …)`) fires once per model call with a
// **mutable** `messages` array — the channel measured to reach the model (see
// workflow-dev's `opencode/plugin.ts` for the measurements). That event carries
// no `source` field, so the "only once per session" half that `source ==
// "startup"` gives Claude Code is this file's job: a Set of session ids. The
// script is asked with `--message {"source":"startup"}`, so it behaves exactly
// as it does on Claude Code while the payload shape stays the script's.
//
// Install by symlink. OpenCode loads direct `.ts`/`.js` files from
// `~/.config/opencode/plugins/`, but this plugin's own checkout sits one level
// below it (`~/.config/opencode/plugins/lbecjx/local-backlog/`), so this file is
// not picked up on its own:
//
//   ln -s ~/.config/opencode/plugins/lbecjx/local-backlog/opencode/plugin.ts \
//         ~/.config/opencode/plugins/local-backlog.ts

import { execFileSync } from "node:child_process"
import { existsSync } from "node:fs"
import { join } from "node:path"

// `import.meta.dir` is Bun's (which is what OpenCode runs plugins on);
// `import.meta.dirname` is Node's, which can exercise this file's logic without
// Bun. Taking whichever exists keeps one implementation.
const HERE = import.meta.dir ?? import.meta.dirname ?? "."
const SCRIPT = join(HERE, "..", "scripts", "session-start-list.sh")

// The project the session belongs to. The script resolves `local-backlog/`
// relative paths by design — so it behaves the same when a human runs it by
// hand — while this plugin process runs in the *service's* directory, which is
// not the session's. Without pinning the cwd every call would silently look in
// the wrong project and find nothing to say. `location` is what the plugin ctx
// exposes for it (measured 2.0.19).
function projectDir(ctx: any): string | undefined {
  // Checked for a *usable* value rather than coalesced: `??` only falls through
  // on null/undefined, so an empty-string `directory` would win the coalesce and
  // then fail the falsy guard below — silently disabling the list even though
  // `location.project.directory` held the answer.
  const dir = ctx?.location?.directory
  if (typeof dir === "string" && dir) return dir
  const project = ctx?.location?.project?.directory
  return typeof project === "string" && project ? project : undefined
}

// Ask the script for the list in `--message` mode: plain text back when there is
// something to show, nothing (exit 0, empty stdout) when there is not. `ok` is
// false only when the script could not run at all (a nonzero exit, or the 5s
// timeout) — the caller must not treat that as "nothing to show", or a single
// transient failure would be remembered as a permanent empty backlog.
function list(cwd: string): { ok: boolean; text?: string } {
  let out = ""
  try {
    out = execFileSync("bash", [SCRIPT, "--message", JSON.stringify({ source: "startup" })], {
      cwd,
      encoding: "utf8",
      timeout: 5000,
    })
  } catch {
    return { ok: false }
  }
  return { ok: true, text: out.trim() || undefined }
}

// Injecting into the model's own context — the only channel measured to reach
// the model from a context hook. The part-array shape is mandatory: a plain
// string `content` crashes the request (measured, 2.0.19).
function intoModelContext(event: any, text: string): boolean {
  if (!Array.isArray(event?.messages)) return false
  event.messages.push({ role: "user", content: [{ type: "text", text: `[local-backlog] ${text}` }] })
  return true
}

export default {
  id: "local-backlog",

  async setup(ctx: any) {
    // Session ids already shown the list. The context hook fires on every model
    // call and OpenCode's event has no `source` field to gate on, so the "only
    // once per session" half lives here. Bounded by the sessions one server
    // process sees; a restart re-opens every session at most once.
    const opened = new Set<string>()

    await ctx.session.hook("context", async (event: any) => {
      const cwd = projectDir(ctx)
      if (!cwd) return

      // Scoped to local-backlog projects. The script's own marker gate would say
      // the same, but checking here keeps a subprocess off every model call in a
      // project that does not use the plugin.
      if (!existsSync(join(cwd, "local-backlog", ".backlog-config.json"))) return

      const session = String(event?.sessionID ?? "")
      if (!session || opened.has(session)) return

      const result = list(cwd)
      // A failed run is not an answer: leave the session unmarked so the next
      // model call retries, instead of turning one transient failure (a timeout
      // on a large backlog) into a permanently missing list. Only a clean run
      // marks the session — empty backlog and all.
      if (!result.ok) return
      opened.add(session)
      if (result.text) intoModelContext(event, result.text)
    })
  },
}
