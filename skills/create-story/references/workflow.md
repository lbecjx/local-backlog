<!--
local-backlog — a local issue/story tracker for Claude Code, no cloud account needed
Copyright (C) 2026  Luis Becerra

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version. See LICENSE for the full text.
-->

# Create Local Story — Detailed Workflow

## Philosophy

`backlog/` is the issue tracker of a project that has none. It's the source of truth
for "what's left to do," and it lives **versioned in git** because it's project
documentation, not ephemeral agent state.

Important contrast with the rest of the workflow:

| Folder | Visible | In git | What it is |
|---|---|---|---|
| `backlog/` | Yes | Yes | Project backlog — durable, written by the human |
| `.workflow-dev/context/` | No | No (gitignored) | Agent working memory — regenerable |

## Flow

### Step 0: External tracker or local?

Phrases like "create a story" don't say *where*. If the project has an external tracker reachable
in the session (an MCP tool with `jira`/`atlassian` in the name) or `REPO.md`
already declares one as an active integration, **ask before creating anything**:
does it go to that tracker or to the local backlog? If there's no signal of one at all,
proceed directly — local is the only real option. If the human already made it
clear in their request ("to the local backlog," "backlog"), don't ask either.

### Step 1: Locate the project root and the prefix

```bash
git rev-parse --show-toplevel   # fall back to cwd if this fails
```

`backlog/` always goes at the root. Never inside `apps/`, `src/`, or any
subfolder — even if the story is specific to one package in a monorepo. The
story's code is global to the repo, not per-package.

**The prefix (`NB`, `PAY`, whatever) is per-project, not hardcoded, and the
code counter is persisted alongside it** in `backlog/.backlog-config.json`:

```json
{ "prefix": "NB", "lastCode": 3 }
```

It's created exactly once, the first time `backlog/` doesn't exist yet:

1. Suggest a prefix derived from the repo/folder name (e.g. `notebooks` → `NB`,
   `payments-api` → `PAY`) and let the human confirm or change it
2. Create the file with that prefix and `lastCode: 0`
3. From then on, always read the prefix and counter from there — never ask for the prefix again, never recompute the counter by scanning files

If the folder already exists but the config doesn't (backlogs created before this
mechanism existed): infer the prefix from the pattern of existing filenames
(`^([A-Z]+)-\d{4}-`), infer `lastCode` as the highest number found, and
write the config so this inference never has to run again.

### Step 2: Compute the next code

**The counter lives in the config, not derived from what files are on disk.** This is
deliberate: computing the next number by scanning `backlog/<PREFIX>-*.md`
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
✅ NB-0001 created — backlog/NB-0001-syntax-highlighting-codeblock.md
   Add syntax highlighting to CodeBlock with Shiki.

   To work on it: /workflow-dev:init backlog/NB-0001-syntax-highlighting-codeblock.md
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
/local-backlog:create-story   → creates <PREFIX>-XXXX in backlog/
          ↓
/workflow-dev:init backlog/<PREFIX>-XXXX-....md   → builds persistent context from that story
          ↓
/workflow-dev:plan → /workflow-dev:implement → /workflow-dev:validate
```

The backlog story is the **input** to `/workflow-dev:init`, just like an external tracker's ticket.
That's why the template includes explicit ACs: it's exactly what `/workflow-dev:init` looks
for when parsing a `.md` as a story (see `skills/init/references/workflow.md`, Step 1-alt).

## What this skill does NOT do

- **Doesn't update the status** of existing stories — that's manual, or handled by another skill
- **Doesn't prioritize the backlog** — doesn't reorder or suggest what to do first
- **Doesn't implement anything** — it only captures the story
- **Doesn't delete or renumber** existing stories
