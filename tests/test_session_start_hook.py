# local-backlog — a local issue/story tracker for Claude Code, no cloud account needed
# Copyright (C) 2026  lbecjx
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version. See LICENSE for the full text.

# Tests for the SessionStart hook (scripts/session-start-list.sh). Drives the
# real script as a subprocess against a throwaway local-backlog/ project, the
# same way a new session invokes it: JSON on stdin, JSON envelope on stdout.

import json
import re
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
HOOK = REPO_ROOT / "scripts" / "session-start-list.sh"


def make_project(tmp_path, marker=True):
    repo = tmp_path / "proj"
    backlog = repo / "local-backlog"
    backlog.mkdir(parents=True)
    if marker:
        (backlog / ".backlog-config.json").write_text(
            json.dumps({"prefix": "QA", "lastCode": 0, "gitignored": True})
        )
    return repo, backlog


def write_story(backlog, code, *, status="Not Started", zone="Backlog",
                priority="Medium", title=None, raw=None):
    path = backlog / f"{code}-story.md"
    if raw is not None:
        path.write_text(raw)
        return path
    title = title or f"{code} title"
    path.write_text(
        f"""# {code} · {title}

| Field | Value |
|---|---|
| **Code** | {code} |
| **Type** | Task |
| **Priority** | {priority} |
| **Status** | {status} |
| **Zone** | {zone} |

---

## Description
A test story.
"""
    )
    return path


def run_hook(repo, source="startup"):
    return subprocess.run(
        [str(HOOK)],
        cwd=repo,
        input=json.dumps({"source": source}),
        capture_output=True,
        text=True,
    )


def context_of(result):
    payload = json.loads(result.stdout)
    return payload["hookSpecificOutput"]["additionalContext"]


def listed_codes(result):
    return re.findall(r"^\| ([A-Z]{2,6}-\d{4}) \|", context_of(result), re.M)


def test_lists_only_not_started(tmp_path):
    repo, backlog = make_project(tmp_path)
    write_story(backlog, "QA-0001", status="Not Started")
    write_story(backlog, "QA-0002", status="In Progress")
    write_story(backlog, "QA-0003", status="Blocked")
    write_story(backlog, "QA-0004", status="Done")

    result = run_hook(repo)

    assert result.returncode == 0
    assert listed_codes(result) == ["QA-0001"]


def test_excludes_archive_zone_even_when_not_started(tmp_path):
    repo, backlog = make_project(tmp_path)
    write_story(backlog, "QA-0001", zone="Archive")
    write_story(backlog, "QA-0002", zone="Backlog")
    write_story(backlog, "QA-0003", zone="Planner")

    result = run_hook(repo)

    assert listed_codes(result) == ["QA-0002", "QA-0003"]


def test_silent_without_the_marker(tmp_path):
    repo, backlog = make_project(tmp_path, marker=False)
    write_story(backlog, "QA-0001")

    result = run_hook(repo)

    assert result.returncode == 0
    assert result.stdout == ""


def test_silent_on_a_non_startup_source(tmp_path):
    repo, backlog = make_project(tmp_path)
    write_story(backlog, "QA-0001")

    result = run_hook(repo, source="resume")

    assert result.returncode == 0
    assert result.stdout == ""


def test_silent_when_nothing_is_not_started(tmp_path):
    repo, backlog = make_project(tmp_path)
    write_story(backlog, "QA-0001", status="Done")

    result = run_hook(repo)

    assert result.returncode == 0
    assert result.stdout == ""


def test_skips_a_malformed_story_without_failing(tmp_path):
    repo, backlog = make_project(tmp_path)
    write_story(backlog, "QA-0001")
    write_story(backlog, "QA-0999", raw="# QA-0999 · no metadata rows\n\nnothing here\n")

    result = run_hook(repo)

    assert result.returncode == 0
    assert listed_codes(result) == ["QA-0001"]


def test_orders_by_priority_then_code(tmp_path):
    repo, backlog = make_project(tmp_path)
    write_story(backlog, "QA-0003", priority="Low")
    write_story(backlog, "QA-0001", priority="High")
    write_story(backlog, "QA-0002", priority="Medium")
    write_story(backlog, "QA-0004", priority="Medium")

    result = run_hook(repo)

    assert listed_codes(result) == ["QA-0001", "QA-0002", "QA-0004", "QA-0003"]


def test_caps_at_ten_and_reports_the_remainder(tmp_path):
    repo, backlog = make_project(tmp_path)
    for n in range(1, 13):
        write_story(backlog, f"QA-{n:04d}", priority="Low")

    result = run_hook(repo)

    assert len(listed_codes(result)) == 10
    context = context_of(result)
    assert "+2 more" in context
    assert "/local-backlog:open-backlog" in context


def test_output_is_a_labelled_session_start_envelope(tmp_path):
    repo, backlog = make_project(tmp_path)
    write_story(backlog, "QA-0001", priority="High")

    result = run_hook(repo)

    payload = json.loads(result.stdout)
    assert payload["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    context = payload["hookSpecificOutput"]["additionalContext"]
    assert context.startswith("local-backlog — stories not started:")
    assert "| QA-0001 |" in context
    assert "| High |" in context


def test_title_with_json_specials_and_pipe_still_parses(tmp_path):
    repo, backlog = make_project(tmp_path)
    write_story(backlog, "QA-0001", title='quo"te back\\slash pipe|x')

    result = run_hook(repo)

    # context_of parses the JSON — it raises here if the envelope is invalid.
    context = context_of(result)
    row = next(line for line in context.splitlines() if line.startswith("| QA-0001 |"))
    cells = [cell.strip() for cell in row.strip("|").split("|")]
    assert len(cells) == 3
    assert '"' not in row
    assert "\\" not in row
    assert "pipe/x" in row


def test_a_crlf_story_is_listed(tmp_path):
    repo, backlog = make_project(tmp_path)
    (backlog / "QA-0001-story.md").write_bytes(
        b"# QA-0001 \xc2\xb7 crlf story\r\n\r\n"
        b"| **Code** | QA-0001 |\r\n"
        b"| **Priority** | High |\r\n"
        b"| **Status** | Not Started |\r\n"
        b"| **Zone** | Backlog |\r\n"
    )

    result = run_hook(repo)

    assert listed_codes(result) == ["QA-0001"]


def test_a_cr_in_the_title_keeps_the_envelope_valid(tmp_path):
    repo, backlog = make_project(tmp_path)
    (backlog / "QA-0001-story.md").write_bytes(
        b"# QA-0001 \xc2\xb7 cr title\r\n\n"
        b"| **Code** | QA-0001 |\n"
        b"| **Priority** | High |\n"
        b"| **Status** | Not Started |\n"
        b"| **Zone** | Backlog |\n"
    )

    result = run_hook(repo)

    context = context_of(result)  # a raw \r here would make this raise
    assert "QA-0001" in context
    assert "\r" not in context


def test_a_tab_in_title_or_priority_keeps_the_columns(tmp_path):
    repo, backlog = make_project(tmp_path)
    write_story(backlog, "QA-0001", title="Tab\there", priority="Hi\tgh")

    result = run_hook(repo)

    row = next(line for line in context_of(result).splitlines() if line.startswith("| QA-0001 |"))
    cells = [cell.strip() for cell in row.strip("|").split("|")]
    assert cells == ["QA-0001", "Tab here", "Hi gh"]


def test_silent_when_the_zone_script_is_missing(tmp_path):
    repo, backlog = make_project(tmp_path)
    write_story(backlog, "QA-0001", zone="Archive")
    # A hook copied into a plugin root that has no skills/ — get-zone.sh is
    # absent, so the zone can't be read and nothing should be listed (rather
    # than the Archive story leaking through).
    fake_root = tmp_path / "plugin"
    (fake_root / "scripts").mkdir(parents=True)
    shutil.copy(HOOK, fake_root / "scripts" / "session-start-list.sh")

    result = subprocess.run(
        [str(fake_root / "scripts" / "session-start-list.sh")],
        cwd=repo,
        input=json.dumps({"source": "startup"}),
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert result.stdout == ""
