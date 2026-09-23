---
name: create-story
description: Creates a structured story file in the project's local-backlog/ folder, with an auto-incrementing <PREFIX>-XXXX code (prefix chosen per-project on first use). For projects without access to an external issue tracker. Use when the user says "create story", "new story", or "add to backlog".
---

<!--
local-backlog — a local issue/story tracker for Claude Code, no cloud account needed
Copyright (C) 2026  lbecjx

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version. See LICENSE for the full text.
-->

# Create Local Story

Creates a story in `local-backlog/` with an auto-incrementing code, in a structured ticket format. This is the local-project substitute for an external tracker's ticket — the output is designed to be consumed directly by `/workflow-dev:init`.

## When to use

- The project has no cloud-based issue tracker (or the human doesn't want to use it) and needs a tracked backlog
- The human wants to capture pending work discovered mid-session before it gets lost
- Converting a vague idea into a structured, actionable story

## When NOT to use

- The project uses an external issue tracker → use that flow in `/workflow-dev:init` instead
- The item is a trivial one-line fix being done right now — just do it

## Execution

**Before executing, read all files in `references/` for the detailed workflow and the story template.**

### Phase 0: Confirm this should be local, not an external tracker

Trigger phrases like "create a story" are ambiguous on their own — they don't say
*where*. Before creating anything:

1. Check whether external-tracker tooling is reachable in this session (an MCP tool whose name
   contains `jira` or `atlassian` — e.g. via a tool search). Also check
   `.workflow-dev/context/REPO.md` if it exists: does it list one as a required/active
   integration?
2. **If that tooling is available or the repo context says one is in use** → stop
   and ask the human explicitly: "This project has an external issue tracker available — should the
   story go there, or stay in the local backlog (`local-backlog/`)?" Proceed
   with this skill only if they confirm local.
3. **If no such signal is found at all** → proceed directly, no need to ask — local
   is the only option that actually works here.
4. **If the human's request already disambiguates** ("add to the local backlog",
   "backlog", "no external tracker") → skip the check, they already told you where.

This check runs once per invocation, not per story in a batch request.

### Phase 1: Locate the backlog, its prefix, and its git-tracking preference

1. Find the repo root (`git rev-parse --show-toplevel`; if not a git repo, use the current working directory)
2. Look for `local-backlog/` at the root. Also check for the legacy `backlog/` name (this
   plugin used that name before `local-backlog/`) — if found, don't silently treat it as
   "doesn't exist": that's a migration case, handled by `/local-backlog:fix`. Tell the human
   a legacy `backlog/` folder was found and suggest running `/local-backlog:fix` to migrate
   it, rather than creating a second, parallel `local-backlog/` folder.
3. **If neither exists — this is first use for this project:**
   a. Ask the human what prefix to use for story codes: 2-5 uppercase letters, project-specific (e.g. a repo called `notebooks` → `NB`, `payments-api` → `PAY`). Suggest one derived from the repo/folder name as a default, but let the human override it.
   b. Ask the human whether `local-backlog/` should be gitignored or tracked in git. This is
      a real tradeoff, not a formality: unlike `.workflow-dev/context/` (regenerable agent
      state — losing it just means re-deriving it later), a backlog's stories are
      irreplaceable, human-authored content. **Gitignored** means the backlog lives only on
      this machine, is never backed up by git, and is permanently lost if this folder or
      machine is ever lost — the right choice for a maintainer's own working notes in a repo
      meant to be published/distributed to others (a plugin, a public library), where those
      notes shouldn't ship to end users. **Tracked** means it's versioned with the rest of
      the repo, survives clones and backups, and is visible to anyone with repo access — the
      right choice when the backlog is itself legitimate project documentation. Don't default
      silently to either — ask.
   c. Create `local-backlog/`
   d. Write `local-backlog/.backlog-config.json` with the prefix, the counter starting at 0,
      and the git-tracking choice:
      ```json
      { "prefix": "NB", "lastCode": 0, "gitignored": false }
      ```
      (using whatever prefix and choice were actually given — this example just shows the shape)
   e. If `gitignored: true` was chosen, add `local-backlog/` to `.gitignore` now (creating
      `.gitignore` if the project doesn't have one yet). If `false`, do nothing further —
      the folder is meant to be tracked normally.
   f. Write `local-backlog/.backlog-statuses.json` with the 3 default statuses —
      a separate file, deliberately: ticket numbering (`.backlog-config.json`)
      and `Status` typing are unrelated concerns that happen to both be
      per-project config:
      ```json
      {
        "statuses": [
          { "name": "Not Started", "color": "neutral" },
          { "name": "In Progress", "color": "blue" },
          { "name": "Done", "color": "green" }
        ]
      }
      ```
   g. Tell the human the folder, the prefix, and the git-tracking choice were set up
4. **If `local-backlog/` already exists** → read `local-backlog/.backlog-config.json` for
   `prefix`, `lastCode`, and `gitignored`.
   - If `.backlog-config.json` is missing or incomplete (backlog created before this
     mechanism existed): infer the prefix from existing filenames (`^([A-Z]+)-\d{4}-`) if
     not already known, infer `lastCode` as the highest number found across existing
     `<PREFIX>-*.md` filenames (0 if none), and write it immediately so this inference never
     has to run again.
   - If `gitignored` is missing from an otherwise-current config (backlog created before
     *that* field existed): this is exactly the Step 3b question, just asked retroactively
     instead of at creation time — ask it now, once, and write the answer in. Don't infer or
     default it silently.
   - If `.backlog-statuses.json` is missing (backlog created before *that* mechanism
     existed, even if `.backlog-config.json` is already current): create it with the same 3
     defaults shown above.
   - Once `gitignored` is known (whether just read or just asked), enforce it: if `true`,
     confirm `local-backlog/` is actually listed in `.gitignore` (add it if missing — a human
     could have hand-edited `.gitignore` since), AND check whether it's already tracked
     (`git ls-files local-backlog/ | head -1`) — adding a path to `.gitignore` does nothing
     to files already committed, so a retroactive `true` answer also needs
     `git rm -r --cached local-backlog/` to actually untrack it (leave the files on disk;
     this only removes them from git's index). If `false`, do nothing further.
   - If there are no stories AND no config, fall back to Step 3a.
5. **Never** create `local-backlog/` inside a subdirectory of the repo — it always lives at the root
6. **`local-backlog/`'s git-tracking status is the human's own choice, made once** (Step 3b,
   or retroactively per Step 4) — don't silently re-decide it, and don't assume either answer
   by default the way earlier versions of this skill did (always tracked, never gitignored).
7. **The prefix is fixed for the life of the project** — once `.backlog-config.json` exists, never ask again and never change it without the human explicitly requesting a rename (which would require renaming every existing story file too — treat that as its own deliberate task, not something to do in passing).

### Phase 2: Determine the next code

**The counter lives in `.backlog-config.json` (`lastCode`), not in the filesystem
listing.** This is deliberate: deriving the next number by scanning existing files
(`ls local-backlog/<PREFIX>-*.md`, take the max, +1) has a real bug — if the
highest-numbered story ever gets deleted, the next scan silently reuses its
number. A persisted counter can't regress just because a file disappeared.

1. Read `lastCode` from `.backlog-config.json` (see Phase 1 step 4 for what to do
   if it's missing)
2. Next code = `lastCode + 1`, zero-padded to 4 digits (`lastCode: 7` → `<PREFIX>-0008`)
3. After successfully writing the story file (Phase 4), update the config with the
   new `lastCode` — do this as the last step, so a failed/aborted write doesn't
   burn a number
4. For a batch of N stories in one request: increment in memory for each one, then
   persist the final `lastCode` once at the end (see "Creating several stories at once")
5. **Never reuse a code, ever** — not for a deleted file, not to fill a gap left by
   one. Gaps are permanent. The counter only moves forward.

### Phase 3: Gather the story content

Extract what you can from the conversation context first — do NOT interrogate the human about things already discussed in the session.

Ask only about what's genuinely missing or ambiguous. You need:

- **Title** — short, imperative, descriptive
- **Type** — Story / Bug / Task / Spike
- **Priority** — High / Medium / Low
- **Labels** — one or more, lowercase, comma-separated (e.g. `notebook, python`). Infer from context first: what part of the repo/monorepo does this touch? A story about a specific app/package usually gets that app's label plus the repo-wide one (e.g. in a monorepo with a shared `notebook` scope and per-app scopes, python-specific work gets `notebook, python`, not just `python`). There's no fixed label vocabulary — it's whatever taxonomy makes sense for this project; check existing stories' labels before inventing a new one for the same concept
- **Description** — what and why, with enough substance to be actionable months later
- **Acceptance Criteria** — concrete and verifiable. If the human can't articulate them, propose a draft from the description and let them correct it
- **Technical notes** — constraints, gotchas, affected files, prior findings (pull these from the session if they came up)

If several fields are already clear from context, present a **complete draft** and ask "anything to adjust?" instead of asking field by field. Interrogating the human about what they just explained is the main failure mode of this skill.

### Phase 4: Write the file

1. Filename: `local-backlog/<PREFIX>-XXXX-brief-description.md`
   - `brief-description` is kebab-case, in the language the human is writing in, max ~5 words
   - Example (prefix `NB`): `NB-0001-syntax-highlighting-codeblock.md`
2. Use the template from `references/template.md`
3. Fill every section — mark genuinely unknown items with ⬜ rather than inventing content

### Phase 5: Confirm

Tell the human:
- The code assigned and the file path
- A one-line summary of what was captured
- That it can be picked up later with `/workflow-dev:init local-backlog/<PREFIX>-XXXX-....md`
- That the backlog can be browsed with `/local-backlog:open-backlog`

## Creating several stories at once

If the human asks for multiple stories in one go (e.g. "create the 3 pending ones we noted"):

- Assign consecutive codes in the order the human listed them, incrementing `lastCode` in memory for each one (don't re-read the config between them)
- Present all of them as one batch for review before writing, not one at a time
- Write the files only after approval, then persist the final `lastCode` to the config in a single update

## Principles

- **The story must survive time** — write it so someone reading it in 6 months, with zero session context, can act on it. Include the *why*, not just the *what*
- **Extract, don't interrogate** — mine the conversation for content before asking
- **Acceptance Criteria are the contract** — vague ACs make a useless story; push for verifiable ones
- **Codes are permanent** — never renumber existing stories, never reuse a code
- **The backlog is not a status tracker** — this skill creates stories; updating status as work progresses is `/local-backlog:update-status`'s job
