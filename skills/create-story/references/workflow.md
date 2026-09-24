<!--
local-backlog — a local issue/story tracker for Claude Code, no cloud account needed
Copyright (C) 2026  lbecjx

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version. See LICENSE for the full text.
-->

# Create Local Story — Detailed Workflow

## Philosophy

`local-backlog/` is the issue tracker of a project that has none. It's the source of truth
for "what's left to do." Whether it lives **versioned in git** or stays **gitignored** is a
per-project choice the human makes once (see Step 1) — not a fixed rule, because the right
answer depends on the project: a repo meant to be published/distributed (a plugin, a public
library) usually shouldn't ship the maintainer's own working notes to end users, while a
project where the backlog is itself legitimate shared documentation should track it.

Important contrast with the rest of the workflow:

| Folder | Visible | In git | What it is |
|---|---|---|---|
| `local-backlog/` | Yes | Human's choice (see Step 1) | Project backlog — durable, written by the human |
| `.workflow-dev/context/` | No | No (gitignored) | Agent working memory — regenerable |

The key difference from `.workflow-dev/context/`: that folder is *always* gitignored because
losing it costs nothing (it's re-derivable from the repo and conversation). A backlog's
stories are irreplaceable, human-authored content — gitignoring it is a real, permanent
data-loss risk if the machine or folder is ever lost, not just an inconvenience. That's why
this is asked rather than defaulted.

## Flow

### Step 0: External tracker or local?

Phrases like "create a story" don't say *where*. If the project has an external tracker reachable
in the session (an MCP tool with `jira`/`atlassian` in the name) or `REPO.md`
already declares one as an active integration, **ask before creating anything**:
does it go to that tracker or to the local backlog? If there's no signal of one at all,
proceed directly — local is the only real option. If the human already made it
clear in their request ("to the local backlog," "backlog"), don't ask either.

### Step 1: Locate the project root, the prefix, and the git-tracking choice

```bash
git rev-parse --show-toplevel   # fall back to cwd if this fails
```

`local-backlog/` always goes at the root. Never inside `apps/`, `src/`, or any
subfolder — even if the story is specific to one package in a monorepo. The
story's code is global to the repo, not per-package.

Check for a legacy `backlog/` folder too (this plugin used that name before
`local-backlog/`) — if one exists, this is a migration case for `/local-backlog:fix`, not a
fresh first-use. Don't create a second, parallel `local-backlog/` alongside an existing
`backlog/`.

**The prefix (`NB`, `PAY`, whatever) is per-project, not hardcoded, and the
code counter is persisted alongside it** in `local-backlog/.backlog-config.json`:

```json
{ "prefix": "NB", "lastCode": 3, "gitignored": false }
```

The project's known `Status` values and the color each renders as in
`/local-backlog:open-backlog`'s viewer live in a **separate** file,
`local-backlog/.backlog-statuses.json` — ticket numbering and `Status` typing are
unrelated concerns that happen to both be per-project config, so they don't
share a file:

```json
{
  "statuses": [
    { "name": "Not Started", "color": "neutral" },
    { "name": "In Progress", "color": "blue" },
    { "name": "Done", "color": "green" }
  ]
}
```

`color` must be one of the names defined in
`skills/update-status/references/status-colors.json` — that file is
authoritative, not this doc; read it rather than guessing or reusing a name
from memory, since it can gain or lose entries independently of this text.
The `statuses` list is what makes `Status` a closed set rather than free text:
`/local-backlog:update-status` rejects any value not in it, and the viewer
gives an unrecognized value a distinct "needs attention" color instead of
silently treating it as one of the known ones.

Both config files, and the git-tracking choice, are settled exactly once, the first time
`local-backlog/` doesn't exist yet:

1. Suggest a prefix derived from the repo/folder name (e.g. `notebooks` → `NB`,
   `payments-api` → `PAY`) and let the human confirm or change it
2. Ask whether `local-backlog/` should be gitignored or tracked (see Philosophy, above, for
   the actual tradeoff — this is not a formality)
3. Create `.backlog-config.json` with that prefix, `lastCode: 0`, and the `gitignored`
   choice; create `.backlog-statuses.json` with the 3 default `statuses` shown above — a
   human can add more later (see `/local-backlog:update-status`'s own docs for how), but
   don't ask about the statuses up front; the defaults cover the overwhelming majority of
   stories
4. If `gitignored: true`, add `local-backlog/` to `.gitignore` now (creating it if the
   project has none)
5. From then on, always read the prefix, counter, and git-tracking choice from
   `.backlog-config.json` and the statuses from `.backlog-statuses.json` — never ask for the
   prefix or the git-tracking choice again, never recompute the counter by scanning files

If the folder already exists but `.backlog-config.json` doesn't (backlogs
created before this mechanism existed): infer the prefix from the pattern of
existing filenames (`^([A-Z]+)-\d{4}-`), infer `lastCode` as the highest number
found, and write the config so this inference never has to run again. If
`.backlog-statuses.json` doesn't exist yet either (even on an otherwise-current
backlog, since it was introduced later than `.backlog-config.json`): create it
with the same 3 defaults. If `gitignored` is missing from an otherwise-current config (it
was introduced later still): ask the Step 1.2 question retroactively, once, and write the
answer in — don't infer or default it silently, and don't leave it unasked indefinitely.
If the retroactive answer is `true`, also check whether `local-backlog/` is already tracked
(`git ls-files local-backlog/ | head -1`) — adding it to `.gitignore` has no effect on files
already committed, so untrack it explicitly with `git rm -r --cached local-backlog/` (the
files stay on disk; this only drops them from git's index).

### Step 2: Compute the next code

**The counter lives in the config, not derived from what files are on disk.** This is
deliberate: computing the next number by scanning `local-backlog/<PREFIX>-*.md`
and taking the max has a real bug — if the story with the highest number gets
deleted, the next scan "forgets" that number ever existed and hands it out again. A
persisted counter can't regress just because a file disappeared.

1. Read `lastCode` from `.backlog-config.json`
2. Next code = `lastCode + 1`, zero-padded to 4 digits (`lastCode: 7` → `<PREFIX>-0008`)
3. Only after successfully writing the story file (Step 5), update `lastCode`
   in the config — that way a failed attempt doesn't burn a number
4. **Deleted codes or gaps: never reused, never backfilled.** The
   counter only moves forward.

### Step 3: Gather the content

**Mine the conversation first.** Most of the time this skill gets invoked
after the human already explained the problem in the session. Re-read that context
and put together a draft.

Only then ask, and only for what's genuinely missing. Asking field by field about
things the human just explained is this skill's main failure mode.

**When the human doesn't know the ACs:** don't leave them empty or ask about them in
the abstract. Propose a concrete set derived from the description and let them correct
it. It's much easier to correct a draft than to write one from scratch.

**Translate session findings into technical notes.** If something like "watch out,
this breaks tests X" or "this collides with prohibition Y in REPO.md" came up during
the conversation, that goes into Technical Notes. It's information that gets lost if it isn't captured.

### Step 4: File name

`<PREFIX>-XXXX-brief-description.md`

- kebab-case
- In the language the human is writing in
- Max ~5 words — the full title goes inside the file
- No accents in the filename (avoids encoding issues across systems)

Examples (prefix `NB`):
- `NB-0001-syntax-highlighting-codeblock.md`
- `NB-0002-fix-title-apps-node.md`
- `NB-0003-extract-shared-nav-sidebar.md`

### Step 5: Write and confirm

Use `references/template.md`. Then report:

```
✅ NB-0001 created — local-backlog/NB-0001-syntax-highlighting-codeblock.md
   Add syntax highlighting to CodeBlock with Shiki.

   To work on it: /workflow-dev:init local-backlog/NB-0001-syntax-highlighting-codeblock.md
```

## Batch creation

When the human asks for several at once ("create the 3 we noted"):

1. Draft all 3 in full from the context
2. Present them together, summarized, for review
3. Write only after the OK
4. Consecutive codes, in the order the human mentioned them

Don't present them one at a time and wait for confirmation between each — that's
friction with no value once the human already said "create the 3."

## Relationship to the rest of the workflow

```
/local-backlog:create-story   → creates <PREFIX>-XXXX in local-backlog/
          ↓
/workflow-dev:init local-backlog/<PREFIX>-XXXX-....md   → builds persistent context from that story
          ↓
/workflow-dev:plan → /workflow-dev:implement → /workflow-dev:validate
```

The backlog story is the **input** to `/workflow-dev:init`, just like an external tracker's ticket.
That's why the template includes explicit ACs: it's exactly what `/workflow-dev:init` looks
for when parsing a `.md` as a story (see `skills/init/references/workflow.md`, Step 1-alt).

## What this skill does NOT do

- **Doesn't update the status** of existing stories — use `/local-backlog:update-status`
- **Doesn't prioritize the backlog** — doesn't reorder or suggest what to do first
- **Doesn't implement anything** — it only captures the story
- **Doesn't delete or renumber** existing stories
