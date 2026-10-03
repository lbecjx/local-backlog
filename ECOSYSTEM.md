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

**Version:** 0.0.1 — **Last updated:** 2026-10-03T20:09:18Z (UTC, `date -u
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

There is no API for "is plugin X installed/enabled right now." Two
generic checks exist instead — pick based on what the integration
actually needs to know:

1. **Is it installed in this session?** Check whether the other plugin's
   slash commands/skills appear in the list of what's currently
   available (e.g. a skill/tool search for its name). Tells you it's
   enabled right now; says nothing about whether this *project* uses it.
2. **Does this project actually use it?** Check for a stable file or
   folder the other plugin is known to leave in a project once it's been
   used there — a config file, a marker written on first use, anything
   that doesn't disappear between sessions. This is almost always the
   right check for a contract, since "installed but never used in this
   project" should behave the same as "not installed."

Either way, the calling skill states — in its own "ECOSYSTEM SECTION,"
never here — which specific check it uses and which specific plugin it's
checking for. If the check comes back negative, the integration is
skipped entirely and the skill continues exactly as it would standalone —
no warning, no degraded mode, nothing left half-done.

**Markers (check 2), one row per plugin in the ecosystem.** This table is
the same in every plugin's copy of this file. Adding a plugin to the
ecosystem means adding its row here, in every copy, in the same sitting
(see "Changing this file").

| Plugin | Marker — exists at the repo root when the project uses it |
|---|---|
| `local-backlog` | `local-backlog/.backlog-config.json` |
| `workflow-dev` | `.workflow-dev/context/REPO.md` |

This file is documentation only. It holds no rule about what any skill
does with a detection result — those rules live only in the calling
skill's own "ECOSYSTEM SECTION."

## How a skill declares an integration

Only a skill that invokes another plugin's skill declares anything. The
convention is the same in every skill, so it can be found and checked
mechanically:

1. The skill has a section titled exactly `## ECOSYSTEM SECTION`, at the
   end of its `SKILL.md`.
2. The first line of that section is
   `Full contract and how-to: see \`../../ECOSYSTEM.md\`.`
3. Below it, `Rules:` followed by numbered rules. Each rule states the
   trigger, the detection check (see above), the exact invocation, and
   what to do when the check is negative (skip).
4. The first line under the skill's `## Execution` heading is exactly
   `Read ECOSYSTEM SECTION.` Nothing else in the skill — outside that
   section — mentions another plugin, names its skills, or explains the
   integration.
5. The section holds rules to invoke another plugin's skill, nothing
   else: no explanations, no installation advice, no marker
   declarations.

A skill with no integration has no such section and no such line.

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

- **0.0.1** (2026-10-03T20:09:18Z)
  - Plugins integrate only by invoking each other's skills, with no hard dependency.
  - Two generic presence checks and a markers table, one row per plugin.
  - Format a skill follows to declare an integration.
