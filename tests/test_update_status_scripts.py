# local-backlog — a local issue/story tracker for Claude Code, no cloud account needed
# Copyright (C) 2026  lbecjx
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version. See LICENSE for the full text.

# Tests for update-status's read-only board reader (get-board.sh). Drives the
# real script as a subprocess against a scratch local-backlog/ project.

import json
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GET_BOARD = REPO_ROOT / "skills" / "update-status" / "scripts" / "get-board.sh"

STORY = "# {code} · test\n\n| **Status** | Not Started |\n"


def write_story(backlog, code):
    path = backlog / f"{code}-story.md"
    path.write_text(STORY.format(code=code))
    return path


def write_board(backlog, planner=(), archive=()):
    (backlog / ".backlog-board.json").write_text(
        json.dumps({"planner": list(planner), "archive": [{"code": c} for c in archive]})
    )


def get_board(story_path):
    return subprocess.run([str(GET_BOARD), str(story_path)], capture_output=True, text=True)


def test_reports_planner(tmp_path):
    backlog = tmp_path / "local-backlog"
    backlog.mkdir()
    story = write_story(backlog, "GB-0001")
    write_board(backlog, planner=["GB-0001"])
    result = get_board(story)
    assert result.returncode == 0
    assert result.stdout.strip() == "planner"


def test_reports_archive(tmp_path):
    backlog = tmp_path / "local-backlog"
    backlog.mkdir()
    story = write_story(backlog, "GB-0001")
    write_board(backlog, archive=["GB-0001"])
    result = get_board(story)
    assert result.returncode == 0
    assert result.stdout.strip() == "archive"


def test_reports_backlog_when_in_neither_list(tmp_path):
    backlog = tmp_path / "local-backlog"
    backlog.mkdir()
    story = write_story(backlog, "GB-0001")
    write_board(backlog, planner=["GB-0002"], archive=["GB-0003"])
    result = get_board(story)
    assert result.returncode == 0
    assert result.stdout.strip() == "backlog"


def test_archive_wins_when_a_code_is_in_both_lists(tmp_path):
    # Overlap can only come from an externally-edited board; the viewer resolves
    # it archive-first, so the reader must agree (otherwise the skill's
    # "don't touch an archived story" guard would miss it).
    backlog = tmp_path / "local-backlog"
    backlog.mkdir()
    story = write_story(backlog, "GB-0001")
    write_board(backlog, planner=["GB-0001"], archive=["GB-0001"])
    result = get_board(story)
    assert result.returncode == 0
    assert result.stdout.strip() == "archive"


def test_missing_board_file_is_backlog(tmp_path):
    backlog = tmp_path / "local-backlog"
    backlog.mkdir()
    story = write_story(backlog, "GB-0001")  # no board file written
    result = get_board(story)
    assert result.returncode == 0
    assert result.stdout.strip() == "backlog"


def test_corrupt_board_fails_loudly(tmp_path):
    backlog = tmp_path / "local-backlog"
    backlog.mkdir()
    story = write_story(backlog, "GB-0001")
    (backlog / ".backlog-board.json").write_text("{not json")
    result = get_board(story)
    assert result.returncode == 1
    assert "invalid JSON" in result.stderr
