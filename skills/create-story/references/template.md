<!--
local-backlog — a local issue/story tracker for Claude Code, no cloud account needed
Copyright (C) 2026  lbecjx

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version. See LICENSE for the full text.
-->

# Template: backlog/<PREFIX>-XXXX-brief-description.md

`<PREFIX>` is the project's prefix, defined once in `backlog/.backlog-config.json`
(e.g. `NB`) — it's not re-asked for every story, it's read from there.

```markdown
# <PREFIX>-XXXX · [Short imperative title]

| Field | Value |
|---|---|
| **Code** | <PREFIX>-XXXX |
| **Type** | Story / Bug / Task / Spike |
| **Priority** | High / Medium / Low |
| **Status** | Not Started |
| **Labels** | label1, label2 |
| **Created** | YYYY-MM-DD |
| **Updated** | YYYY-MM-DD |

---

## Description

[What needs to be done and WHY. Enough context for someone with no memory
of the session where this was born to understand it 6 months from now. If it comes
from a concrete finding, include the finding — not just the conclusion.]

## User Story

**As** [role — usually the repo owner, or the notebook's reader]
**I want** [concrete capability]
**So that** [real benefit, not a tautology]

> Skip this section if the type is Task or Spike and forcing it would feel artificial.

## Acceptance Criteria

1. ⬜ [Verifiable criterion — can be answered yes/no by looking at the result]
2. ⬜ [...]
3. ⬜ [...]

**States:** ⬜ pending | 🔧 in progress | ✅ done

## Technical Notes

- [Constraints, gotchas, decisions already made]
- [Affected files/modules, with path]
- [Relevant prior findings — e.g. "this breaks tests X because Y"]
- [Dependencies on other stories: "blocked by <PREFIX>-XXXX"]

## Definition of Done

- [ ] Acceptance Criteria met
- [ ] `/workflow-dev:validate` passes
- [ ] Visual verification (if it touches UI/CSS/styles)
- [ ] Tests added or updated if behavior changed
- [ ] Committed following Conventional Commits

## History

- YYYY-MM-DDTHH:MM:SSZ — Created (Status: Not Started)

---

> Generated with `/local-backlog:create-story`. To work on it: `/workflow-dev:init backlog/<PREFIX>-XXXX-....md`
```

## Notes on the template

| Section | Required | Notes |
|---|---|---|
| Metadata table | Yes | `Status` always starts as `Not Started` |
| Labels | Yes (can be just one) | Lowercase, comma-separated, no extra spaces: `notebook, python`. A story can have several — no limit. Used for filtering in the viewer (`/local-backlog:open-backlog`). There's no fixed list of valid labels — they get defined per project (e.g. here: `notebook`, `node`, `python`) |
| Description | Yes | This is what saves the story from being forgotten — don't skimp |
| User Story | No | Skip for Task/Spike if it feels forced |
| Acceptance Criteria | Yes | Without verifiable ACs the story is useless |
| Technical Notes | Yes | Can say "none" if there genuinely are none |
| Definition of Done | Yes | Adjust the items to the type of work (e.g. drop "visual verification" if it doesn't touch UI) |
| History | Yes | Starts with a single "Created" entry — see Content rules below for how it grows |

## Content rules

- **The story's `Status` lives here, nowhere else.** Use `/local-backlog:update-status` to change it — never edit the `Status` row by hand.
- **Every `Status` change gets a line in `## History`, appended — never edited or removed.** Format: `- YYYY-MM-DDTHH:MM:SSZ — Status: <old> → <new>` — full ISO 8601 datetime in UTC (`Z` suffix), not just a date, from a real clock (`date -u +%Y-%m-%dT%H:%M:%SZ`), never hand-written or estimated. Storing it in UTC is deliberate: the raw value stays unambiguous no matter who or what writes it. Converting to local time, relative phrasing ("3 days ago"), or any other display format is `/local-backlog:open-backlog`'s viewer's job, not something baked into the stored value. `/local-backlog:update-status`'s script does all of this — including keeping the `Updated` field in sync — in one pass; this rule exists for the rare case something other than that skill needs to touch `Status` directly. Without it, a story's real history — when it actually started, when it stalled, when it shipped — only exists in scattered git commit dates, if the file was even committed incrementally.
- **The ACs are the contract.** If they say "retry 3 times with exponential backoff 1s/4s/16s," keep ALL of that detail — don't summarize it to "add retries."
- **Never invent content to fill a section.** What isn't known gets marked ⬜ and asked about.
