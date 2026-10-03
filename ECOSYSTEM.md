<!--
lbecjx Plugins Ecosystem — shared cross-plugin integration contract.
Copyright (C) 2026  lbecjx

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version. See LICENSE for the full text
(in each plugin's own repo).

This file is the same, by hand, in every lbecjx plugin that participates
in the ecosystem — no plugin's copy is more authoritative than another's;
each is just a
hardcoded duplicate. There is no fetch, no pull, no shared runtime copy:
editing this contract means editing it in every plugin's repo, in the
same sitting, and bumping **Version** below so the two can be compared by
eye. See "Changing this file."
-->

# lbecjx Plugins Ecosystem

**Version:** 0.0.4 — **Last updated:** 2026-10-03T14:27:47Z (UTC, `date -u
+%Y-%m-%dT%H:%M:%SZ`, never typed or estimated). Bump both on every
content change (see "Changing this file"). There is no automated way to
tell a plugin's copy is stale; **Version** is the drift check compared by
eye, and **Last updated** is the tiebreaker if two plugins' copies were
ever edited independently and now disagree — whichever timestamp is later
is the one to propagate, and the other plugin's edit must be re-applied
on top of it, not discarded.

This file documents cross-plugin integration between `lbecjx`'s own Claude
Code plugins. Every plugin that participates keeps an identical copy of
this exact file at its repo root.

## Philosophy

- **Soft coupling only.** Every plugin in this ecosystem must work fully
  standalone — on its own, with no other `lbecjx` plugin installed. Nothing
  here may become a hard requirement.
- **No shared runtime between plugins exists.** Claude Code has no event
  bus, no pub/sub, and no hook mechanism that lets one plugin detect or
  react to another plugin's skill running (hooks match on `tool_name`, not
  on plugin/skill identity). The only way one plugin's skill reaches
  another's is an agent explicitly invoking it — a judgment call driven by
  the calling skill's own instructions, not a deterministic system trigger.
- **Invoking a skill needs nothing from the skill being invoked.** A skill
  is callable by anyone, from anywhere, the moment it's installed — it
  doesn't need its own instructions to "allow" being called by another
  plugin. Consequently, an integration's instructions belong **only** in
  the *calling* skill. The skill being called needs no matching section —
  adding one there would document nothing that changes how it behaves.
- **Never use `plugin.json` `dependencies` for this.** That field forces
  the dependency to be enabled before the dependent plugin loads — a hard
  coupling that breaks the first rule above. Presence is always checked at
  run time instead (see below), and its absence is always a silent no-op,
  never an error.

## Detecting another plugin's presence

There is no API for "is plugin X installed/enabled right now." The only
practical signal is a file the other plugin is already known to leave on
disk — a config file, a marker it writes on first use, anything stable.
A calling skill states, in its own "ECOSYSTEM SECTION," which specific
file it checks for and which specific plugin that file indicates. If the
marker is absent, the integration is skipped entirely and the skill
continues exactly as it would standalone — no warning, no degraded mode,
nothing left half-done.

This file never names a specific plugin, a specific marker file, or a
specific contract — doing so would make this copy diverge from what every
other `lbecjx` plugin needs, defeating the point of it being identical
everywhere. All of that — which plugins exist, what each one's presence
marker is, what contracts exist between which plugins, what each one does
and why — lives only in the calling skill's own "ECOSYSTEM SECTION," in
whichever plugin actually implements it.

## Changing this file

1. Edit this file, including bumping **Version**, setting **Last updated**
   to a real UTC clock (`date -u +%Y-%m-%dT%H:%M:%SZ`, never typed or
   estimated), and adding a line to Version History below.
2. Make the exact same edit, by hand, in every other plugin's copy of this
   same file — there is no fetch, no script, no automation that does this
   for you. Both copies must end up byte-identical.
3. Bump each affected plugin's own version and note the change in its own
   `CHANGELOG.md` — same release discipline as any other shared file (see
   `local-backlog`'s `skills/open-backlog/dist/`, never hand-edited either,
   though that one *is* a one-way build artifact — this file is edited
   directly, in both places, every time).

## Version History

- **0.0.4** (2026-10-03T14:27:47Z) — Removed the presence-marker table
  and the Contracts section entirely — both named specific plugins
  (`local-backlog`, `workflow-dev`), which this file must never do: it
  has to stay byte-identical across any `lbecjx` plugin, present or
  future, with zero edits needed to adopt a new one. Which plugins
  exist, each one's presence marker, and what contracts exist between
  them now live only in the calling skill's own "ECOSYSTEM SECTION."
- **0.0.3** (2026-10-03T14:26:22Z) — Contracts section cut down to a bare
  index (name, caller/called, status, pointer) — the previous
  what/why/implemented-in bullets still restated rule content that
  belongs only in the calling skill. Contract #1's rationale moved into
  `workflow-dev:init`'s own ECOSYSTEM SECTION.
- **0.0.2** (2026-10-03T04:25:19Z) — Contracts section rewritten as a
  registry, not a rulebook: dropped the Trigger/Presence
  check/Action-style bullets (they duplicated the operative rule already
  written in the calling skill's own file) in favor of
  participants/what/why/implemented-in/status. No behavior changed.
- **0.0.1** (2026-10-03T04:17:46Z) — Initial contract. Philosophy,
  presence-marker table, Contract #1 (start a story, `workflow-dev:init`
  → `local-backlog:update-status`) documented and implemented on the
  `workflow-dev` side. Contract #2 (close a story) specified, not yet
  implemented on either side.
