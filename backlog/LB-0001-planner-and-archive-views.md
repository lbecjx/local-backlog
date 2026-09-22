# LB-0001 · Add Planner (Kanban board) and Archive views to the viewer

| Field | Value |
|---|---|
| **Code** | LB-0001 |
| **Type** | Story |
| **Priority** | Medium |
| **Status** | Not Started |
| **Labels** | backlog-viewer, ui |
| **Created** | 2026-09-22 |
| **Updated** | 2026-09-22 |

---

## Description

Right now `/local-backlog:open-backlog`'s viewer shows every story in a single flat
list (the Backlog), with no way to manually organize a working set or to see what's
already finished. This story adds two new views on top of the same underlying story
files, changing the Backlog from "every story" to "stories not yet claimed by
either of the other two views":

- **Planner** — a Kanban board. One column per status defined in the project's
  `.backlog-statuses.json` (so a project's own status set drives the board layout,
  same file `/local-backlog:update-status` already reads). A human drags a story
  from the Backlog into the Planner to start actively organizing it; once there, it
  no longer shows in the Backlog list. Inside the Planner, dragging a story from one
  column to another changes its `Status` to match the column it lands in — this is
  meant to be the primary way `Status` gets changed going forward, replacing (or
  complementing — see open questions) manually invoking `/local-backlog:update-status`.
- **Archive** — where finished or abandoned stories go. A `Done` story can be sent
  here. So can an *active* one (`Not Started`/`In Progress`) — archiving an
  incomplete story is how a human abandons it without deleting it, and requires
  going through a confirmation dialog with an optional (can be left blank) textarea
  to note why it's being archived. A story reaches the Archive only by explicit
  human action: a right-click context menu on its card, or an entry in the story
  detail view's own options menu — never automatically just because its `Status`
  became `Done` on the Planner.

Recap of the three views, in the human's own words from the session this was
captured in: "Backlog, stories que aun no estan en el planner. Planner: stories que
el humano manualmente esta organizando alli. Y el archivo, donde van las que
manualmente el usuario manda con click derecho, o desde un menu de opciones en el
detalle."

## User Story

**As** someone using the viewer to manage a real backlog day to day
**I want** to move stories into a Planner board and archive finished/abandoned ones
**So that** the Backlog list only ever shows things I haven't started organizing yet,
and I have a Kanban view plus a history of what's done, instead of one long flat list

## Acceptance Criteria

1. ⬜ A new "Planner" tab exists alongside "Backlog" and "Archive", at the top of
   the app
2. ⬜ The Planner renders one column per entry in the project's
   `.backlog-statuses.json` `statuses` array, in the order that file lists them
3. ⬜ A story can be dragged from the Backlog list into the Planner; once there, it
   no longer appears in the Backlog list
4. ⬜ Dragging a story from one Planner column to another updates that story's
   `Status` field to the target column's status name, persisted back to the
   story's `.md` file via a write endpoint added to the viewer's local server
   (see Technical Notes)
5. ⬜ A new "Archive" tab exists, showing stories that have been explicitly
   archived
6. ⬜ A story can be archived via a right-click context menu on its card
7. ⬜ A story can be archived via an entry in the story detail view's options menu
8. ⬜ Archiving shows a confirmation dialog with an optional textarea for a reason;
   confirming with an empty textarea is allowed
9. ⬜ Archiving a story that is not already `Done` sets its `Status` to `Done` and
   its `Resolution` to either `Done` or `Won't Do`, chosen by the human in the
   confirmation dialog (see Technical Notes — `Resolution` is a new field, not a
   4th value added to `.backlog-statuses.json`)
10. ⬜ A story only ever appears in exactly one of Backlog / Planner / Archive at a
    time — never in two views at once, never in none

## Technical Notes

- **Planner/Archive membership** is tracked in a new, separate per-project file
  — parallel to `.backlog-config.json`/`.backlog-statuses.json`, not a field on
  each story's own metadata table. Keeps story `.md` files themselves untouched
  by pure UI-organization state; exact filename/shape is a `/local-backlog:plan`
  detail, not decided here.
- **Persisting a Status change made by dragging a card in the Planner** needs the
  same write path `/local-backlog:update-status`'s script uses (`Status` +
  `Updated` + `## History` together, one atomic write). The viewer is currently
  served read-only via `python3 -m http.server` — this story adds a small
  write-enabled endpoint to that local server (started by
  `open-backlog.sh`/`idle_server.py`) that the Planner's drag handler calls,
  which in turn invokes the same logic `update-status.sh` already uses. Exact
  endpoint shape is a `/local-backlog:plan` detail.
- **`Won't Do` is NOT a new value added to `.backlog-statuses.json`.** `Status`
  stays closed to the project's existing set (`Not Started`/`In Progress`/`Done`
  by default) — archiving an incomplete story always sets `Status` to `Done`.
  Instead, a new **`Resolution`** field (`Done` | `Won't Do`) is written only at
  archive time, mirroring how GitHub/Jira separate "closed" (a status) from *why*
  it closed (a resolution/reason). This field, its exact metadata-table row
  placement, and whether `update-status.sh` needs to learn about it are
  `/local-backlog:plan` details.
- Relevant existing code: `src/components/StoryList.tsx` / `StoryCard.tsx` (current
  flat Backlog rendering), `src/lib/backlogConfig.ts` (`fetchBacklogStatuses`,
  already reads `.backlog-statuses.json`), `src/hooks/useBacklogStories.ts`
  (current story-loading/sorting logic — new views will likely need their own
  filtered slices of the same story list, not a separate fetch).
- No drag-and-drop library is currently a dependency of `backlog-viewer` — picking
  one (or building it with the native HTML Drag and Drop API) is a `/local-backlog:plan`
  decision, not assumed here.

## Definition of Done

- [ ] Acceptance Criteria met
- [x] Open questions below resolved (with the human) before implementation starts
- [ ] Visual verification in the browser (this is UI/drag-and-drop — automated
      tests alone won't catch a layout or interaction regression)
- [ ] Tests added for the new view logic (filtering which stories show where) and
      the archive confirmation flow
- [ ] Committed following Conventional Commits

## Open Questions for the Human

All resolved 2026-09-22 — kept here for the record, decisions folded into the ACs
and Technical Notes above:

- ✅ Archive view is named "Archive" (matches the ACs and how it was already being
  discussed) — the human's original capture ("el historial de stories DONE o
  quiza archivo no se") was genuinely undecided, no strong preference either way
- ✅ Planner/Archive membership: a separate per-project tracking file
- ✅ Planner drag write path: a write endpoint added to the viewer's local server
- ✅ Archiving an incomplete story: always `Status: Done`, plus a new
  `Resolution: Done | Won't Do` field
- ✅ Navigation: tabs at the top (Backlog / Planner / Archive)

## History

- 2026-09-22T05:38:48Z — Created (Status: Not Started)

---

> Generated with `/local-backlog:create-story`. To work on it: `/workflow-dev:init backlog/LB-0001-planner-and-archive-views.md`
