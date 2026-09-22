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
