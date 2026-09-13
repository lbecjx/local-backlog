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
