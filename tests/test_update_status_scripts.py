# local-backlog — a local issue/story tracker for Claude Code, no cloud account needed
# Copyright (C) 2026  lbecjx
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version. See LICENSE for the full text.

# Tests for update-status's Zone reader/writer (get-zone.sh / set-zone.sh).
# Drives the real scripts as subprocesses against a scratch story file —
# LB-0014 moved zone membership off a separate `.backlog-board.json` and
# onto the story's own `| **Zone** |` row, so there is no board file left
# to set up here.

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GET_ZONE = REPO_ROOT / "skills" / "update-status" / "scripts" / "get-zone.sh"
SET_ZONE = REPO_ROOT / "skills" / "update-status" / "scripts" / "set-zone.sh"

STORY = "# {code} · test\n\n| **Status** | Not Started |\n| **Note** |  |\n"


def write_story(backlog, code):
    path = backlog / f"{code}-story.md"
    path.write_text(STORY.format(code=code))
    return path


def zone_row(story_path):
    for line in story_path.read_text().splitlines():
        if line.startswith("| **Zone**"):
            return line.split("|")[2].strip()
    return None


def get_zone(story_path):
    return subprocess.run([str(GET_ZONE), str(story_path)], capture_output=True, text=True)


def set_zone(story_path, zone):
    return subprocess.run([str(SET_ZONE), str(story_path), zone], capture_output=True, text=True)


def test_get_zone_reports_backlog_when_row_is_absent(tmp_path):
    backlog = tmp_path / "local-backlog"
    backlog.mkdir()
    story = write_story(backlog, "GB-0001")
    result = get_zone(story)
    assert result.returncode == 0
    assert result.stdout.strip() == "backlog"


def test_get_zone_reports_planner(tmp_path):
    backlog = tmp_path / "local-backlog"
    backlog.mkdir()
    story = write_story(backlog, "GB-0001")
    set_zone(story, "planner")
    result = get_zone(story)
    assert result.returncode == 0
    assert result.stdout.strip() == "planner"


def test_get_zone_reports_archive(tmp_path):
    backlog = tmp_path / "local-backlog"
    backlog.mkdir()
    story = write_story(backlog, "GB-0001")
    set_zone(story, "archive")
    result = get_zone(story)
    assert result.returncode == 0
    assert result.stdout.strip() == "archive"


def test_get_zone_defaults_to_backlog_on_an_unrecognized_value(tmp_path):
    backlog = tmp_path / "local-backlog"
    backlog.mkdir()
    story = write_story(backlog, "GB-0001")
    text = story.read_text() + "| **Zone** | Bogus |\n"
    story.write_text(text)
    result = get_zone(story)
    assert result.returncode == 0
    assert result.stdout.strip() == "backlog"


def test_set_zone_inserts_the_row_for_a_legacy_story(tmp_path):
    backlog = tmp_path / "local-backlog"
    backlog.mkdir()
    story = write_story(backlog, "GB-0001")
    result = set_zone(story, "planner")
    assert result.returncode == 0
    assert result.stdout.strip() == "Zone: planner"
    assert zone_row(story) == "Planner"


def test_set_zone_replaces_an_existing_row(tmp_path):
    backlog = tmp_path / "local-backlog"
    backlog.mkdir()
    story = write_story(backlog, "GB-0001")
    set_zone(story, "planner")
    result = set_zone(story, "archive")
    assert result.returncode == 0
    assert zone_row(story) == "Archive"
    # Exactly one Zone row survives, never a second one appended.
    assert story.read_text().count("| **Zone**") == 1


def test_set_zone_is_idempotent(tmp_path):
    backlog = tmp_path / "local-backlog"
    backlog.mkdir()
    story = write_story(backlog, "GB-0001")
    set_zone(story, "backlog")
    before = story.read_text()
    set_zone(story, "backlog")
    assert story.read_text() == before


def test_set_zone_rejects_an_invalid_zone(tmp_path):
    backlog = tmp_path / "local-backlog"
    backlog.mkdir()
    story = write_story(backlog, "GB-0001")
    result = set_zone(story, "bogus")
    assert result.returncode != 0
    assert "not a valid zone" in result.stderr
    assert zone_row(story) is None


def test_set_zone_missing_file_fails(tmp_path):
    result = set_zone(tmp_path / "nope.md", "planner")
    assert result.returncode != 0
    assert "No such file" in result.stderr


def test_set_zone_fails_loudly_with_no_zone_or_note_row_to_anchor_on(tmp_path):
    # Found by adversarial review: a story predating the Note field has
    # nothing for the insert branch to match, so awk silently copies the
    # file through unchanged — this must refuse outright, not report
    # success for a write that never happened.
    backlog = tmp_path / "local-backlog"
    backlog.mkdir()
    story = backlog / "GB-0001-story.md"
    story.write_text("# GB-0001 · test\n\n| **Status** | Not Started |\n")
    before = story.read_text()

    result = set_zone(story, "planner")

    assert result.returncode != 0
    assert "neither a" in result.stderr
    assert story.read_text() == before
