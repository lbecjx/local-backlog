<!--
local-backlog — a local issue/story tracker for Claude Code, no cloud account needed
Copyright (C) 2026  lbecjx

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version. See LICENSE for the full text.
-->

# Changelog

All notable changes to this plugin are documented here. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/), versioning follows
[Semantic Versioning](https://semver.org/).

## 1.15.0

- `open-backlog` prints `PROJECT:<name>` and `ROOT:<path>` alongside
  `OPENED:`/`STORIES:`, and the skill states the project name in its report.
- `open-backlog` asks which project to open when the conversation points at a
  different project than the cwd-resolved one and both have a `local-backlog/`.
- Add `--resolve-only` to report the resolution without opening anything.
- Add `--root <path>` to open a specific project's backlog.

## 1.14.1

- Fix the bundled viewer showing "Failed to list …/local-backlog/: 404": the
  open-backlog server now stages the project's data at `/local-backlog/`, the
  path `backlog-viewer` 0.6.0 fetches, instead of `/backlog/`.

## 1.14.0

- An archived story is now frozen: `update-status.sh` refuses every status change
  on a story in the `Archive` zone, writing nothing and pointing at unarchive.
  Unarchiving (`set-zone.sh`) changes only the `Zone` row. Archiving is never a
  side effect of a status change, and re-archiving over HTTP is a no-op rather
  than a 500.
- Fix data loss in `update-status.sh` when appending to a `## History` section
  whose last entry wrapped onto continuation lines.
- `tests/test_update_status.py` is now the dedicated `update-status.sh` suite,
  moved out of `tests/test_idle_server.py` and extended.
- `/local-backlog:update-status` documents bulk/batch requests and states that
  the guided flow runs for every change.

## 1.13.0

- Add a `SessionStart` hook that lists stories still `Not Started` when a session
  opens in a project using this plugin.
- On OpenCode, where `hooks/hooks.json` is not read, the same list is delivered
  by `opencode/plugin.ts`.
- The hook reads only this plugin's `local-backlog/` data, is silent without
  `local-backlog/.backlog-config.json` or outside a genuine startup session, and never writes.

## 1.12.0

- The bundled viewer now reads a story's `Zone` from the story's own
  `| **Zone** |` row instead of `.backlog-board.json`, matching 1.10.0's move of
  the zone onto the story. Zone changes still go through `/api/board`.
  Re-vendored from `backlog-viewer` 0.6.0.

## 1.11.0

- `ECOSYSTEM.md` documents how `lbecjx` plugins detect and call each other.
- `/local-backlog:update-status`, run with nobody to answer, now also adds a
  started story to the Planner board.

## 1.10.0

- Zone (Backlog/Planner/Archive) is now a field on the story itself — a
  `| **Zone** |` row, same as `Status`/`Resolution`/`Note` — instead of
  membership in a separate `local-backlog/.backlog-board.json`. That file is
  retired entirely: `get-board.sh`/`set-board.sh` are replaced by
  `get-zone.sh`/`set-zone.sh`, which read and write the story file directly.
- `/local-backlog:fix` backfills `Zone` on every story from an existing
  `.backlog-board.json` and deletes it once every story is migrated
  (`migrate-zone-field.sh`, replacing `migrate-board-archive.sh`).
- The bundled viewer still reads/writes `.backlog-board.json` until its own
  companion change (`backlog-viewer`'s `BV-0007`) ships and this plugin's
  vendored `dist/` is rebuilt from it — that re-vendor is a separate,
  follow-up release.

## 1.9.1

- `/local-backlog:update-status` now keeps a story's file mode, and removes its
  lock and temp file when it is interrupted.
- The story model describes the History lines that are not status transitions.

## 1.9.0

- `/local-backlog:fix` now detects stories missing a `## History` section —
  those created before it existed — and adds it after a dry run and confirmation.

## 1.8.0

- The board's `archive` list now stores bare code strings (`["LB-0001"]`),
  matching `planner`. `set-board.sh` rewrites legacy `{ "code": … }` entries on
  its next write, and `get-board.sh` reads bare codes only.
- `/local-backlog:fix` can detect and rewrite legacy `{ "code": … }` archive
  entries (dry run first, confirmation before writing).
- The bundled viewer is rebuilt from `backlog-viewer` `0.2.0`: archived stories
  stay out of the Backlog list, and a card's title is struck through by the
  story's `Resolution`.

## 1.7.0

- Any status change can now carry an optional **note**, not just a move to
  `Done`. `/local-backlog:update-status` asks for a one-line note on every
  transition, and "skip" is a valid answer; when there is nobody to ask, it
  writes one explaining the move instead of letting the change pass silently.
- The note — and the `Resolution`, when the move closes the story — is now
  recorded on the story's `## History` line, after the new status:
  `… — Status: <old> → <new> · Resolution: <value> · Note: <text>`. Each earlier
  transition therefore keeps its own reason, instead of only the most recent one
  surviving in the story's `Note` row.
- The transition line is now written wherever a story's history section ends —
  including when it ends the file, or runs straight into a separator — so a
  transition and the note it carries are never dropped while the command reports
  them as appended. A legacy backfill likewise no longer overwrites an existing
  `Note` row.

## 1.6.0

- `/local-backlog:update-status` now offers to set a story `In Progress` and add
  it to the Planner board in one prompt when you start working on it, so the
  board no longer drifts behind the status. It reads the story's current board
  zone first and only asks when there is something to do — never for a story
  already `In Progress` on the Planner board, never for one in the Archive, and
  never when you're closing a story. Each accepted part goes through its own
  script, and nothing is applied silently.

## 1.5.0

- `/local-backlog:fix` now detects stories that reached `Done` before the
  `Resolution` field existed — they are `Done` with an empty `Resolution` — and
  offers to backfill each with `resolution: Done`, repairing legacy data onto
  the `Status: Done ⇒ Resolution set` invariant. The write goes through the same
  update mechanism a `Done` transition uses and leaves the `Status` and the
  `## History` log untouched, since no status change happens.

## 1.4.0

- A story's **Resolution** is now a field of the story itself, alongside
  `Status`, instead of being recorded in the board's archive list. Moving a
  story to `Done` **requires** a resolution from a fixed set — `Done`,
  `Won't Do`, `Duplicate`, `Cannot Reproduce` — and leaving `Done` clears it.
  The Done transition can also carry a short free-text `Note`. The story
  template now includes both rows, empty until first used.
- The entire story model — the `Status` values with their colors, the
  `Resolution` values, the story's own fields, and the shape of its `## History`
  log — now lives once in `skills/create-story/references/story-model.json`
  (JSON Schema): the single source read by this plugin's scripts and served to
  the viewer, which derives its schema from it. It replaces the separate
  `status-colors.json` and the per-project `.backlog-statuses.json` — statuses
  and resolutions are canonical now, with no per-project list to maintain.
- Archiving no longer stores the resolution and reason in
  `.backlog-board.json` — an archive entry is just `{ "code": … }`, and
  archiving still lands the resolution on the story. The local write endpoints
  validate a resolution against the model and reject a `Done` transition
  without a valid one with a clean `400`.

## 1.3.3

- The story footer now links to `workflow-dev`, and `create-story`'s closing
  note points at it (with the link) when `workflow-dev` isn't already available —
  a discovery nudge for projects using only `local-backlog`, not a dependency.

## 1.3.2

- Rebuilt and re-vendored the bundled viewer so it carries the client-side load
  resilience: a dropped story fetch is retried, and a single unrecoverable story
  no longer fails the whole load.

## 1.3.1

- The viewer's server now uses a larger accept backlog, so the burst of
  parallel requests the viewer fires on startup can no longer overflow the
  listen queue and drop a connection — which previously surfaced as a full
  "Error reading the backlog" for a backlog that actually exists.

## 1.3.0

- Renamed the project backlog folder from `backlog/` to `local-backlog/` — a
  bare `backlog/` was too likely to collide with an unrelated folder a
  project already had for its own purposes. `/local-backlog:fix` now detects
  a legacy `backlog/` folder and offers to migrate it (rename plus updating
  every story's own footer link).
- `/local-backlog:create-story` now asks, once per project on first use,
  whether `local-backlog/` should be gitignored or tracked in git — this
  plugin previously hardcoded "always tracked, never gitignored," which
  turned out to be the wrong default for a plugin/library repo, where a
  maintainer's own working notes shouldn't ship to end users the same way a
  project's real documentation should. The choice persists in
  `.backlog-config.json`'s new `gitignored` field — asked once per project,
  applied consistently from then on, never silently re-decided. When the
  answer is asked retroactively on a folder git already tracks (an existing
  project, or one migrating off the legacy `backlog/` name via
  `/local-backlog:fix`), choosing `gitignored` also runs `git rm -r --cached`
  on it — adding a path to `.gitignore` alone has no effect on files already
  committed.

## 1.2.0

- Added `/local-backlog:update-status` — the only supported way to change a
  story's `Status` now. Its script updates `Status`, `Updated`, and a new
  `## History` section together in one pass, from a real clock
  (`- YYYY-MM-DDTHH:MM:SSZ — Status: <old> → <new>`, full ISO 8601 UTC
  datetime — the raw value stays unambiguous no matter who writes it, and
  converting it to local time or relative phrasing is the viewer's job, not
  baked into storage).
  Before this, a story's real progression — when it actually started, when
  it stalled, when it shipped — only existed in scattered git commit dates,
  if the file was even committed incrementally at each step; the metadata
  table's own `Created`/`Updated` fields are single timestamps, not a log.
- Stories created from the template now start with a `## History` section
  (a single "Created" entry); `/local-backlog:fix` uses the same script
  instead of hand-editing `Status` when a repair changes its value.
- `Status` is a closed set now, not free text. A new file,
  `.backlog-statuses.json` — separate from `.backlog-config.json`, which is
  only about ticket numbering — holds each project's list of valid statuses
  (3 defaults seeded automatically: `Not Started`, `In Progress`, `Done`,
  each with a fixed `color` name). `update-status`'s script rejects a value
  that isn't in that list instead of accepting a typo silently, printing the
  actual known values so the caller can pick a real one or add a new one. A
  project with no `.backlog-statuses.json` keeps accepting any string — this
  only closes the set for projects that have the file.
- The fixed palette of valid `color` names (and the exact Tailwind classes
  each renders as) lives in `skills/update-status/references/status-colors.json`
  — the one file both this plugin's own docs/scripts and
  `/local-backlog:open-backlog`'s viewer read, so neither side can drift
  from the other. `open-backlog.sh` copies it into the served directory
  before opening the browser.

## 1.1.0

- Added `/local-backlog:fix` — diagnoses and fixes a broken or misbehaving
  backlog/viewer (no stories showing, wrong/unknown statuses, malformed
  metadata tables), asking for confirmation before any change and for input
  when a fix is ambiguous. Motivated by a real case: a project with stories
  still on the legacy metadata-key format silently showed every story as
  "Unknown" once that fallback was removed in 1.0.1.
- `/local-backlog:open-backlog` now runs a bundled script file
  (`scripts/open-backlog.sh`) instead of an inline shell block — one
  permission prompt for the whole flow instead of several, and a fixed
  command line stable enough for Claude Code's permission system to remember
  across runs instead of re-prompting every single time.
- The local server it starts (`scripts/idle_server.py`) now shuts itself down
  after 30 minutes with no requests, instead of running forever until the
  machine reboots — a forgotten viewer no longer sits consuming RAM
  indefinitely. Picked up transparently: the next run already checks whether
  the previous server's PID is still alive before reusing it.

## 1.0.1

- Fixed the bundled viewer (`skills/open-backlog/dist/`) to parse story metadata
  tables using only the current, English field keys (`Code`/`Type`/`Priority`/
  `Status`/`Created`/`Updated`). The previous build accepted a legacy Spanish-key
  fallback left over from an earlier template revision; it's been removed since
  no story format in use actually depends on it.
- Corrected author/copyright attribution across the README, per-file copyright
  headers, and plugin/marketplace metadata to use the real author name.

## 1.0.0

- Initial release: `/local-backlog:create-story`, `/local-backlog:open-backlog`,
  and `/local-backlog:help` skills for tracking issues/stories as local Markdown
  files with a searchable, locally-served viewer.
