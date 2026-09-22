# LB-0002 · Add Status History, typed Status, and fix viewer detail/UX gaps

| Field | Value |
|---|---|
| **Code** | LB-0002 |
| **Type** | Story |
| **Priority** | Medium |
| **Status** | Done |
| **Labels** | local-backlog, backlog-viewer |
| **Created** | 2026-09-22 |
| **Updated** | 2026-09-22 |

---

## Description

Retroactive story — this work was already completed, ad hoc, directly in
conversation, before this project adopted `/local-backlog:create-story` +
`/workflow-dev:init` for its own development. Captured here so the backlog has a
real record of it, not because it's about to be planned or implemented.

Three things happened together, across both `local-backlog` and `backlog-viewer`:

1. A story's `Status` had no history — only `Created`/`Updated`, both single
   timestamps that get overwritten. Added a `## History` section to the story
   template (append-only, one line per `Status` change, full ISO 8601 UTC
   datetime) and `/local-backlog:update-status` as the one supported way to change
   `Status` — its script updates `Status`, `Updated`, and `History` together in
   one atomic write, from a real clock.
2. `Status` was free text — any string was silently accepted, typos included. A
   new per-project file, `.backlog-statuses.json` (separate from
   `.backlog-config.json`, which is only about ticket numbering), holds the
   project's valid statuses and their colors; `update-status` rejects anything
   not in that list. The fixed palette of valid color names lives in
   `skills/update-status/references/status-colors.json` — the single file both
   this plugin and the bundled viewer read, so neither side can drift from the
   other (`open-backlog.sh` copies it into the served directory at runtime).
3. Rebuilding `backlog-viewer` to consume the above surfaced several real,
   unrelated UX/correctness gaps in the viewer itself, fixed in the same pass:
   `StoryDetail` was missing status/type/priority/labels/dates that the card
   already showed; dates rendered as raw ISO 8601 UTC instead of a friendly
   local format; the detail header's status badge was stretched to the panel's
   far edge, disconnected from the title; metadata was crammed under the title
   with no hierarchy instead of a separated sidebar (redesigned after looking at
   real GitHub issue/PR pages); a "Not Started" badge's dark-mode background
   color collided with a selected card's own background, making the badge
   invisible; stories rendered oldest-first instead of newest-first; the
   viewer's own `public/backlog/` test fixtures were being copied into `dist/`
   on build (would have shipped fake mock stories inside the real published
   plugin); and several new/existing UI strings were in Spanish despite this
   being a published, general-audience tool.

## User Story

**As** a maintainer of `local-backlog`/`backlog-viewer`
**I want** a real record of this already-completed work in the backlog
**So that** the project's history is legible from `backlog/` alone, not just from
conversation transcripts or scattered CHANGELOG prose

## Acceptance Criteria

1. ✅ `## History` section added to the story template, append-only, ISO 8601 UTC
2. ✅ `/local-backlog:update-status` added — updates `Status`/`Updated`/`History`
   together in one script
3. ✅ `.backlog-statuses.json` added (separate from `.backlog-config.json`),
   closing `Status` to a per-project list
4. ✅ `skills/update-status/references/status-colors.json` added as the single
   source of truth for valid color names, read by both this plugin and the
   viewer (via `open-backlog.sh` copying it into the served directory)
5. ✅ `backlog-viewer`'s `statusColor.ts` reads the palette + a project's
   statuses at runtime instead of a hardcoded 3-value map
6. ✅ `StoryDetail` shows all the metadata `StoryCard` shows, plus priority and
   dates, laid out in a sidebar (not stacked under the title)
7. ✅ Dates render in a friendly, locale-aware format — never raw ISO 8601
8. ✅ Story list sorts newest-first
9. ✅ `backlog-viewer`'s own test fixtures no longer leak into its `dist/` build
10. ✅ All user-facing strings in `backlog-viewer` are in English

## Technical Notes

- Full detail lives in each repo's own `CHANGELOG.md`: `local-backlog`'s `1.2.0`
  entry, and the corresponding (at time of writing, not yet committed)
  `backlog-viewer` entry for this same arc of work.
- No `/workflow-dev:init` context exists for this story and none will be created
  — it's retroactive, already merged in spirit if not yet in a formal PR at time
  of writing.

## Definition of Done

- [x] Acceptance Criteria met
- [x] Tests added (both repos' test suites — see each repo's own test files
      touched in this arc)
- [x] Visual verification in the browser (done repeatedly against real scratch
      projects during this work)
- [ ] Committed following Conventional Commits (commits for this arc are still
      pending in both repos at time this retroactive story was written)

## History

- 2026-09-22T05:52:44Z — Created (Status: Not Started)
- 2026-09-22T05:53:01Z — Status: Not Started → Done

---

> Generated with `/local-backlog:create-story`. Retroactive — this work is already
> complete; there is no `/workflow-dev:init` to run for it.
