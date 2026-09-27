# local-backlog — a local issue/story tracker for Claude Code, no cloud account needed
# Copyright (C) 2026  lbecjx
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version. See LICENSE for the full text.

# Tests for the fix skill's repair scripts. Each drives the real script as a
# subprocess against a scratch local-backlog/ project — the same way the skill
# invokes it — not a mocked helper.

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LIST_SCRIPT = REPO_ROOT / "skills" / "fix" / "scripts" / "list-unresolved-done.sh"
UPDATE_STATUS = REPO_ROOT / "skills" / "update-status" / "scripts" / "update-status.sh"

STORY = """# {code} · test story

| Field | Value |
|---|---|
| **Code** | {code} |
| **Type** | Story |
| **Priority** | Low |
| **Status** | {status} |
| **Resolution** | {resolution} |
| **Note** |  |
| **Labels** | test |
| **Created** | 2026-01-01 |
| **Updated** | 2026-01-01 |

---

## History

- 2026-01-01T00:00:00Z — Created

---
"""


def write_story(backlog, code, status, resolution=""):
    path = backlog / f"{code}-story.md"
    path.write_text(STORY.format(code=code, status=status, resolution=resolution))
    return path


def list_unresolved(backlog):
    result = subprocess.run([str(LIST_SCRIPT), str(backlog)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return result.stdout.split()


def test_lists_only_done_stories_without_a_resolution(tmp_path):
    backlog = tmp_path / "local-backlog"
    backlog.mkdir()
    unresolved = write_story(backlog, "FX-0001", "Done", "")
    write_story(backlog, "FX-0002", "Done", "Done")
    write_story(backlog, "FX-0003", "In Progress", "")
    (backlog / "notes.md").write_text("# not a story\n")  # a stray .md is ignored

    assert list_unresolved(backlog) == [str(unresolved)]


def test_lists_a_legacy_story_with_no_resolution_row(tmp_path):
    # A story created before the Resolution field existed has no such row at
    # all — it must still be detected (the row read treats absent as empty).
    backlog = tmp_path / "local-backlog"
    backlog.mkdir()
    legacy = backlog / "FX-0004-story.md"
    legacy.write_text(
        "# FX-0004 · test story\n\n| Field | Value |\n|---|---|\n"
        "| **Code** | FX-0004 |\n| **Type** | Story |\n| **Priority** | Low |\n"
        "| **Status** | Done |\n| **Labels** | test |\n"
        "| **Created** | 2026-01-01 |\n| **Updated** | 2026-01-01 |\n\n---\n\n"
        "## History\n\n- 2026-01-01T00:00:00Z — Created\n\n---\n"
    )
    assert list_unresolved(backlog) == [str(legacy)]


def test_backfill_touches_only_the_unresolved_done_story(tmp_path):
    backlog = tmp_path / "local-backlog"
    backlog.mkdir()
    unresolved = write_story(backlog, "FX-0001", "Done", "")
    resolved = write_story(backlog, "FX-0002", "Done", "Done")
    in_progress = write_story(backlog, "FX-0003", "In Progress", "")
    resolved_before, in_progress_before = resolved.read_text(), in_progress.read_text()

    for path in list_unresolved(backlog):
        result = subprocess.run(
            [str(UPDATE_STATUS), path, "Done", "--resolution", "Done"], capture_output=True, text=True
        )
        assert result.returncode == 0, result.stderr

    assert "| **Resolution** | Done |" in unresolved.read_text()
    assert resolved.read_text() == resolved_before
    assert in_progress.read_text() == in_progress_before
    # Idempotent: once every Done story has a resolution, nothing is left.
    assert list_unresolved(backlog) == []
