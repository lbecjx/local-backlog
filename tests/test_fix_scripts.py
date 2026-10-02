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

import json
import os
import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LIST_SCRIPT = REPO_ROOT / "skills" / "fix" / "scripts" / "list-unresolved-done.sh"
MIGRATE_SCRIPT = REPO_ROOT / "skills" / "fix" / "scripts" / "migrate-board-archive.sh"
REPAIR_SCRIPT = REPO_ROOT / "skills" / "fix" / "scripts" / "repair-missing-history.sh"
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


def write_board(backlog, board):
    (backlog / ".backlog-board.json").write_text(json.dumps(board))


def read_board(backlog):
    return json.loads((backlog / ".backlog-board.json").read_text())


def migrate(backlog, *args):
    return subprocess.run([str(MIGRATE_SCRIPT), *args, str(backlog)], capture_output=True, text=True)


def test_migrate_dry_run_reports_changes_and_touches_nothing(tmp_path):
    backlog = tmp_path / "local-backlog"
    backlog.mkdir()
    write_board(backlog, {"planner": ["FX-0009"], "archive": [{"code": "FX-0001"}, "FX-0002"]})
    before = (backlog / ".backlog-board.json").read_text()

    result = migrate(backlog)

    assert result.returncode == 0
    assert result.stdout.count('{"code": "FX-0001"} -> "FX-0001"') == 1
    assert "FX-0002" not in result.stdout
    assert (backlog / ".backlog-board.json").read_text() == before


def test_migrate_write_rewrites_legacy_entries_and_is_idempotent(tmp_path):
    backlog = tmp_path / "local-backlog"
    backlog.mkdir()
    write_board(backlog, {"planner": ["FX-0009"], "archive": [{"code": "FX-0001"}, "FX-0002"]})

    result = migrate(backlog, "--write")
    assert result.returncode == 0
    assert read_board(backlog) == {"planner": ["FX-0009"], "archive": ["FX-0001", "FX-0002"]}

    second = migrate(backlog, "--write")
    assert second.returncode == 0
    assert second.stdout == ""
    assert read_board(backlog) == {"planner": ["FX-0009"], "archive": ["FX-0001", "FX-0002"]}


def test_migrate_preserves_unrecognized_entries(tmp_path):
    backlog = tmp_path / "local-backlog"
    backlog.mkdir()
    write_board(backlog, {"planner": [], "archive": [{"code": "FX-0001"}, {"code": 5}, 7]})

    result = migrate(backlog, "--write")

    assert result.returncode == 0
    assert read_board(backlog)["archive"] == ["FX-0001", {"code": 5}, 7]


def test_migrate_missing_directory_fails(tmp_path):
    result = subprocess.run([str(MIGRATE_SCRIPT), str(tmp_path / "nope")], capture_output=True, text=True)
    assert result.returncode == 1


def test_migrate_missing_board_is_a_silent_noop(tmp_path):
    backlog = tmp_path / "local-backlog"
    backlog.mkdir()
    result = migrate(backlog)
    assert result.returncode == 0
    assert result.stdout == ""


def test_migrate_corrupt_board_fails_without_touching_it(tmp_path):
    backlog = tmp_path / "local-backlog"
    backlog.mkdir()
    (backlog / ".backlog-board.json").write_text("{not json")

    result = migrate(backlog, "--write")

    assert result.returncode == 1
    assert "invalid JSON" in result.stderr
    assert (backlog / ".backlog-board.json").read_text() == "{not json"


# A story as it was before `## History` (and the Resolution/Note rows) existed:
# the metadata table is the old shape and the body runs straight into the
# closing rule and footer.
LEGACY_STORY = """# {code} · legacy story

| Field | Value |
|---|---|
| **Code** | {code} |
| **Type** | Story |
| **Priority** | Low |
| **Status** | Not Started |
| **Labels** | test |
| **Created** | 2026-01-01 |
| **Updated** | 2026-01-01 |

---

## Description

Body text.

---

A rule inside the body, which is not the story's own end.

## Definition of Done

- [ ] Done

---

> Generated with `/local-backlog:create-story`.
"""

ENTRY = re.compile(r"^- \d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ — History section added by /local-backlog:fix \(story predates it\)$")


def write_legacy(backlog, code="FX-0001", text=None):
    path = backlog / f"{code}-legacy.md"
    path.write_text(LEGACY_STORY.format(code=code) if text is None else text)
    return path


def repair(backlog, *args):
    return subprocess.run([str(REPAIR_SCRIPT), *args, str(backlog)], capture_output=True, text=True)


def scratch_backlog(tmp_path):
    backlog = tmp_path / "local-backlog"
    backlog.mkdir()
    return backlog


def test_repair_dry_run_lists_the_story_and_touches_nothing(tmp_path):
    backlog = scratch_backlog(tmp_path)
    story = write_legacy(backlog)
    before = story.read_text()

    result = repair(backlog)

    assert result.returncode == 0
    assert result.stdout.split() == [str(story)]
    assert story.read_text() == before


def test_repair_adds_only_the_new_section_before_the_closing_rule(tmp_path):
    backlog = scratch_backlog(tmp_path)
    story = write_legacy(backlog)
    before = story.read_text()

    result = repair(backlog, "--write")

    assert result.returncode == 0
    assert result.stdout.split() == [str(story)]
    after = story.read_text()
    closing = before.rindex("\n---\n\n> Generated") + 1
    # Everything before the closing rule and everything from it on is the
    # original, byte for byte; only the section lands between them.
    assert after.startswith(before[:closing])
    assert after.endswith(before[closing:])
    section = after[closing : len(after) - len(before[closing:])].split("\n")
    assert section[0] == "## History"
    assert section[1] == ""
    assert ENTRY.match(section[2])
    assert section[3:] == ["", ""]
    # Created is untouched and no transition was invented.
    assert "| **Created** | 2026-01-01 |" in after
    assert "Status:" not in after


def test_repair_covers_a_story_with_no_history_and_no_resolution_rows(tmp_path):
    backlog = scratch_backlog(tmp_path)
    story = write_legacy(backlog)
    assert "**Resolution**" not in story.read_text()

    repair(backlog, "--write")

    assert "## History" in story.read_text()


def test_repair_leaves_a_story_that_already_has_history_untouched(tmp_path):
    backlog = scratch_backlog(tmp_path)
    story = write_story(backlog, "FX-0001", "Not Started")
    before = story.read_text()

    result = repair(backlog, "--write")

    assert result.returncode == 0
    assert result.stdout == ""
    assert story.read_text() == before


def test_repair_leaves_an_empty_history_section_untouched(tmp_path):
    backlog = scratch_backlog(tmp_path)
    text = LEGACY_STORY.format(code="FX-0001").replace("---\n\n> Generated", "## History\n\n---\n\n> Generated")
    story = write_legacy(backlog, text=text)

    result = repair(backlog, "--write")

    assert result.returncode == 0
    assert result.stdout == ""
    assert story.read_text() == text


def test_repair_is_idempotent(tmp_path):
    backlog = scratch_backlog(tmp_path)
    story = write_legacy(backlog)

    repair(backlog, "--write")
    once = story.read_text()
    second = repair(backlog, "--write")

    assert second.returncode == 0
    assert second.stdout == ""
    assert story.read_text() == once
    assert once.count("## History") == 1


def test_repair_appends_at_the_end_when_there_is_no_footer(tmp_path):
    backlog = scratch_backlog(tmp_path)
    text = "# FX-0001 · bare\n\n| Field | Value |\n|---|---|\n| **Code** | FX-0001 |\n\n---\n\nbody\n"
    story = write_legacy(backlog, text=text)

    repair(backlog, "--write")

    after = story.read_text()
    assert after.startswith(text)
    assert after[len(text):].split("\n")[:3] == ["", "## History", ""]
    assert ENTRY.match(after.splitlines()[-2])


def test_repair_adds_a_blank_line_when_the_closing_rule_hugs_the_body(tmp_path):
    backlog = scratch_backlog(tmp_path)
    text = "# FX-0001 · tight\n\n- [ ] Done\n---\n\n> Generated with `/local-backlog:create-story`.\n"
    story = write_legacy(backlog, text=text)

    repair(backlog, "--write")

    assert story.read_text().startswith("# FX-0001 · tight\n\n- [ ] Done\n\n## History\n\n- ")


def test_repair_keeps_the_stories_file_mode(tmp_path):
    backlog = scratch_backlog(tmp_path)
    story = write_legacy(backlog)
    story.chmod(0o644)

    repair(backlog, "--write")

    assert story.stat().st_mode & 0o777 == 0o644


def test_repair_only_touches_story_files(tmp_path):
    backlog = scratch_backlog(tmp_path)
    notes = backlog / "notes.md"
    notes.write_text("# not a story\n")

    result = repair(backlog, "--write")

    assert result.returncode == 0
    assert result.stdout == ""
    assert notes.read_text() == "# not a story\n"


def test_repair_missing_directory_fails(tmp_path):
    result = subprocess.run([str(REPAIR_SCRIPT), str(tmp_path / "nope")], capture_output=True, text=True)
    assert result.returncode == 1
    assert "No such directory" in result.stderr


def test_repair_unwritable_story_is_reported_and_left_unchanged(tmp_path):
    backlog = scratch_backlog(tmp_path)
    story = write_legacy(backlog)
    before = story.read_text()
    # A read-only folder blocks the lock and the replace alike; the story must
    # come out untouched with a non-zero exit, not look repaired.
    backlog.chmod(0o555)
    try:
        result = repair(backlog, "--write")
    finally:
        backlog.chmod(0o755)

    assert result.returncode == 1
    assert result.stdout == ""
    assert story.read_text() == before


def test_update_status_refuses_a_legacy_story_until_it_is_repaired(tmp_path):
    backlog = scratch_backlog(tmp_path)
    story = write_legacy(backlog)

    def move(status):
        return subprocess.run([str(UPDATE_STATUS), str(story), status], capture_output=True, text=True, cwd=tmp_path)

    refused = move("In Progress")
    assert refused.returncode == 1
    assert "No '## History' section" in refused.stderr

    repair(backlog, "--write")
    moved = move("In Progress")

    assert moved.returncode == 0, moved.stderr
    lines = story.read_text().splitlines()
    assert ENTRY.match(lines[lines.index("## History") + 2])
    assert re.match(r"^- \S+ — Status: Not Started → In Progress$", lines[lines.index("## History") + 3])
