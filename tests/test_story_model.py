# local-backlog — a local issue/story tracker for Claude Code, no cloud account needed
# Copyright (C) 2026  lbecjx
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version. See LICENSE for the full text.

# The story model documents the lines a story's `## History` section holds; the
# scripts and the template are the other two owners of that format. These tests
# keep the three describing the same set of lines.

import json
import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MODEL = REPO_ROOT / "skills" / "create-story" / "references" / "story-model.json"
TEMPLATE = REPO_ROOT / "skills" / "create-story" / "references" / "template.md"
REPAIR = REPO_ROOT / "skills" / "fix" / "scripts" / "repair-missing-history.sh"
UPDATE_STATUS = REPO_ROOT / "skills" / "update-status" / "scripts" / "update-status.sh"

ISO = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z"
AT = "<at>"
TRANSITION_MARKER = " — Status: "


def history_section():
    return json.loads(MODEL.read_text())["x-story-file"]["historySection"]


def non_transition(name):
    return next(e for e in history_section()["nonTransitionLines"] if e["name"] == name)


def as_regex(line):
    """A pattern for a model line: its literal text, with the `<at>` placeholder as an ISO UTC stamp."""
    before, after = line.split(AT)
    return re.compile(f"^{re.escape(before)}{ISO}{re.escape(after)}$")


def test_the_model_lists_exactly_the_non_transition_lines_the_plugin_writes():
    assert [e["name"] for e in history_section()["nonTransitionLines"]] == ["created", "history-section-added"]


def test_the_transition_line_carries_the_marker():
    assert TRANSITION_MARKER in history_section()["line"]


def test_no_non_transition_line_is_shaped_like_a_transition():
    for entry in history_section()["nonTransitionLines"]:
        assert TRANSITION_MARKER not in entry["line"].replace(AT, "", 1)


def test_transitions_still_require_from_and_to():
    model = json.loads(MODEL.read_text())
    assert model["$defs"]["historyEntry"]["required"] == ["at", "from", "to"]


def test_the_template_carries_the_created_line_the_model_describes():
    line = non_transition("created")["line"].replace(AT, "YYYY-MM-DDTHH:MM:SSZ")
    assert line in TEMPLATE.read_text()


def test_the_template_names_the_line_the_fix_script_writes():
    line = non_transition("history-section-added")["line"].removeprefix(f"- {AT} — ")
    assert line in TEMPLATE.read_text()


def test_the_repair_script_emits_the_line_the_model_describes(tmp_path):
    backlog = tmp_path / "local-backlog"
    backlog.mkdir()
    story = backlog / "MD-0001-story.md"
    story.write_text("# MD-0001 · x\n\n---\n\n> Generated with `x`.\n")

    result = subprocess.run([str(REPAIR), "--write", str(backlog)], capture_output=True, text=True)

    assert result.returncode == 0, result.stderr
    pattern = as_regex(non_transition("history-section-added")["line"])
    assert any(pattern.match(line) for line in story.read_text().splitlines())


def test_update_status_emits_a_transition_not_a_non_transition_line(tmp_path):
    backlog = tmp_path / "local-backlog"
    backlog.mkdir()
    story = backlog / "MD-0001-story.md"
    story.write_text("# MD-0001 · x\n\n| **Status** | Not Started |\n\n---\n\n## History\n\n- 2026-01-01T00:00:00Z — Created (Status: Not Started)\n\n---\n")

    subprocess.run([str(UPDATE_STATUS), str(story), "In Progress"], capture_output=True, text=True, check=True)

    lines = [line for line in story.read_text().splitlines() if line.startswith("- ")]
    assert len(lines) == 2
    created, transition = lines
    assert as_regex(non_transition("created")["line"]).match(created)
    assert re.match(rf"^- {ISO} — Status: Not Started → In Progress$", transition)
    for entry in history_section()["nonTransitionLines"]:
        assert not as_regex(entry["line"]).match(transition)
