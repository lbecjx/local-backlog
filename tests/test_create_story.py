# local-backlog — a local issue/story tracker for Claude Code, no cloud account needed
# Copyright (C) 2026  lbecjx
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version. See LICENSE for the full text.

# Suite for create-story's write-story.sh — the script that assigns a story's
# code at write time, so two sessions creating stories in the same project never
# hand out the same code. Every test drives the real script as a subprocess
# against a scratch local-backlog/ folder.

import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
WRITE_STORY = REPO_ROOT / "skills" / "create-story" / "scripts" / "write-story.sh"

DRAFT = "# {{CODE}} · a story\n\n| **Code** | {{CODE}} |\n\nrun `/workflow-dev:init local-backlog/{{CODE}}-new.md`\n"


@pytest.fixture
def backlog(tmp_path):
    folder = tmp_path / "local-backlog"
    folder.mkdir()
    return folder


def write_config(backlog, **config):
    (backlog / ".backlog-config.json").write_text(json.dumps(config))


def read_config(backlog):
    return json.loads((backlog / ".backlog-config.json").read_text())


def draft(tmp_path, name="draft.md", text=DRAFT):
    path = tmp_path / name
    path.write_text(text)
    return path


def run(backlog, *pairs):
    return subprocess.run(
        [str(WRITE_STORY), str(backlog), *[str(p) for p in pairs]],
        capture_output=True,
        text=True,
    )


def story_files(backlog):
    return sorted(p.name for p in backlog.glob("*.md"))


def test_a_code_taken_by_another_session_is_skipped(tmp_path, backlog):
    # The reported case: lastCode is N, another session already wrote N+1 but
    # its counter write is not visible here — the new story gets N+2.
    write_config(backlog, prefix="QA", lastCode=5, gitignored=True)
    (backlog / "QA-0006-other-session.md").write_text("theirs\n")

    result = run(backlog, "new", draft(tmp_path))

    assert result.returncode == 0, result.stderr
    assert "SKIPPED: QA-0006" in result.stdout
    assert f"CREATED: QA-0007 {backlog}/QA-0007-new.md" in result.stdout
    assert read_config(backlog)["lastCode"] == 7
    assert (backlog / "QA-0006-other-session.md").read_text() == "theirs\n"
    written = (backlog / "QA-0007-new.md").read_text()
    assert "{{CODE}}" not in written
    assert written.count("QA-0007") == 3


def test_the_code_comes_from_the_counter_read_at_write_time(tmp_path, backlog):
    # The draft was shown with QA-0003 (lastCode 2 back then); the counter has
    # since moved to 9 with no files left behind (deleted stories). The counter
    # wins, and a deleted story's code is not reused.
    write_config(backlog, prefix="QA", lastCode=9, gitignored=True)

    result = run(backlog, "new", draft(tmp_path))

    assert result.returncode == 0, result.stderr
    assert story_files(backlog) == ["QA-0010-new.md"]
    assert read_config(backlog)["lastCode"] == 10


def test_the_counter_never_moves_back(tmp_path, backlog):
    write_config(backlog, prefix="QA", lastCode=3, gitignored=True)
    (backlog / "QA-0004-a.md").write_text("a\n")
    (backlog / "QA-0005.md").write_text("b\n")

    result = run(backlog, "new", draft(tmp_path))

    assert result.returncode == 0, result.stderr
    assert "QA-0006-new.md" in story_files(backlog)
    assert read_config(backlog)["lastCode"] == 6


def test_a_batch_gets_consecutive_free_codes_and_one_counter_write(tmp_path, backlog):
    write_config(backlog, prefix="QA", lastCode=1, gitignored=True)
    (backlog / "QA-0003-taken.md").write_text("x\n")

    result = run(backlog, "first", draft(tmp_path, "a.md"), "second", draft(tmp_path, "b.md"), "third", draft(tmp_path, "c.md"))

    assert result.returncode == 0, result.stderr
    created = [line.split()[1] for line in result.stdout.splitlines() if line.startswith("CREATED:")]
    assert created == ["QA-0002", "QA-0004", "QA-0005"]
    assert result.stdout.count("LASTCODE:") == 1
    assert read_config(backlog)["lastCode"] == 5


def test_the_other_config_fields_are_kept(tmp_path, backlog):
    (backlog / ".backlog-config.json").write_text('{ "prefix": "QA", "lastCode": 41, "gitignored": false }\n')

    result = run(backlog, "new", draft(tmp_path))

    assert result.returncode == 0, result.stderr
    assert (backlog / ".backlog-config.json").read_text() == '{ "prefix": "QA", "lastCode": 42, "gitignored": false }\n'


def test_concurrent_runs_get_unique_codes(tmp_path, backlog):
    write_config(backlog, prefix="QA", lastCode=0, gitignored=True)
    drafts = [draft(tmp_path, f"d{i}.md") for i in range(6)]

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda i: run(backlog, f"s{i}", drafts[i]), range(6)))

    assert all(r.returncode == 0 for r in results), [r.stderr for r in results]
    codes = sorted(name[:7] for name in story_files(backlog))
    assert codes == [f"QA-000{n}" for n in range(1, 7)]
    assert read_config(backlog)["lastCode"] == 6
    assert not (backlog / ".create-story.lock").exists()


def test_a_dangling_symlink_counts_as_taken(tmp_path, backlog):
    write_config(backlog, prefix="QA", lastCode=0, gitignored=True)
    (backlog / "QA-0001-link.md").symlink_to(tmp_path / "nowhere.md")

    result = run(backlog, "new", draft(tmp_path))

    assert result.returncode == 0, result.stderr
    assert not (tmp_path / "nowhere.md").exists()
    assert (backlog / "QA-0002-new.md").exists()


@pytest.mark.parametrize("slug", ["", "Upper", "with space", "../escape", "a/b", "acción", "trailing-", "x" * 81])
def test_an_invalid_slug_writes_nothing(tmp_path, backlog, slug):
    write_config(backlog, prefix="QA", lastCode=0, gitignored=True)

    result = run(backlog, slug, draft(tmp_path))

    assert result.returncode == 2
    assert story_files(backlog) == []
    assert read_config(backlog)["lastCode"] == 0


def test_a_draft_without_the_placeholder_writes_nothing(tmp_path, backlog):
    write_config(backlog, prefix="QA", lastCode=0, gitignored=True)

    result = run(backlog, "ok", draft(tmp_path, "good.md"), "bad", draft(tmp_path, "bad.md", "# QA-0002 · literal code\n"))

    assert result.returncode == 2
    assert "{{CODE}}" in result.stderr
    assert story_files(backlog) == []


def test_a_missing_draft_writes_nothing(tmp_path, backlog):
    write_config(backlog, prefix="QA", lastCode=0, gitignored=True)

    result = run(backlog, "new", tmp_path / "missing.md")

    assert result.returncode == 2
    assert story_files(backlog) == []


@pytest.mark.parametrize("args", [[], ["only-dir"], ["dir", "slug"], ["dir", "a", "d", "b"]])
def test_a_wrong_argument_count_is_refused(args):
    result = subprocess.run([str(WRITE_STORY), *args], capture_output=True, text=True)

    assert result.returncode == 2
    assert "Usage" in result.stderr


@pytest.mark.parametrize("config", ['{"lastCode": 1}', '{"prefix": "qa", "lastCode": 1}', '{"prefix": "QA"}', '{"prefix": "QA", "lastCode": "x"}'])
def test_a_bad_config_writes_nothing(tmp_path, backlog, config):
    (backlog / ".backlog-config.json").write_text(config)

    result = run(backlog, "new", draft(tmp_path))

    assert result.returncode == 1
    assert story_files(backlog) == []
    assert (backlog / ".backlog-config.json").read_text() == config
    assert not (backlog / ".create-story.lock").exists()


def test_a_missing_config_writes_nothing(tmp_path, backlog):
    result = run(backlog, "new", draft(tmp_path))

    assert result.returncode == 1
    assert story_files(backlog) == []


def test_a_held_lock_times_out_without_writing(tmp_path, backlog):
    write_config(backlog, prefix="QA", lastCode=0, gitignored=True)
    (backlog / ".create-story.lock").mkdir()

    result = run(backlog, "new", draft(tmp_path))

    assert result.returncode == 1
    assert "Could not acquire" in result.stderr
    assert story_files(backlog) == []
    # Never removes a lock it did not take.
    assert (backlog / ".create-story.lock").is_dir()


def test_a_failed_write_mid_batch_writes_nothing(tmp_path, backlog):
    # A batch is all or nothing: a retry after a failure must not duplicate the
    # stories that were written before it.
    write_config(backlog, prefix="QA", lastCode=0, gitignored=True)
    good = draft(tmp_path, "a.md")
    failing = draft(tmp_path, "b.md")
    # A shim `sed` fails on the second story's draft only.
    shim_dir = tmp_path / "shim"
    shim_dir.mkdir()
    (shim_dir / "sed").write_text(
        f'#!/bin/bash\nfor a in "$@"; do [[ "$a" == "{failing}" ]] && exit 1; done\nexec /usr/bin/sed "$@"\n'
    )
    (shim_dir / "sed").chmod(0o755)
    env = {**os.environ, "PATH": f"{shim_dir}:{os.environ['PATH']}"}

    result = subprocess.run(
        [str(WRITE_STORY), str(backlog), "first", str(good), "second", str(failing)],
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 1
    assert "CREATED:" not in result.stdout
    assert story_files(backlog) == []
    assert read_config(backlog)["lastCode"] == 0
    assert not (backlog / ".create-story.lock").exists()


def test_a_batch_story_can_name_a_siblings_final_code(tmp_path, backlog):
    # The draft for "ui" depends on "api"; another session took api's
    # provisional code, so the reference must follow api to its final code.
    write_config(backlog, prefix="QA", lastCode=43, gitignored=True)
    (backlog / "QA-0044-other.md").write_text("theirs\n")
    api = draft(tmp_path, "api.md", "# {{CODE}} · api\n")
    ui = draft(tmp_path, "ui.md", "# {{CODE}} · ui\n\n- blocked by {{CODE:1}}\n")

    result = run(backlog, "api", api, "ui", ui)

    assert result.returncode == 0, result.stderr
    assert (backlog / "QA-0046-ui.md").read_text() == "# QA-0046 · ui\n\n- blocked by QA-0045\n"


@pytest.mark.parametrize("ref", ["{{CODE:0}}", "{{CODE:3}}", "{{CODE:x}}"])
def test_a_sibling_reference_outside_the_batch_writes_nothing(tmp_path, backlog, ref):
    write_config(backlog, prefix="QA", lastCode=0, gitignored=True)

    result = run(backlog, "a", draft(tmp_path, "a.md"), "b", draft(tmp_path, "b.md", f"# {{{{CODE}}}}\nsee {ref}\n"))

    assert result.returncode == 2
    assert story_files(backlog) == []


def test_a_draft_in_another_encoding_is_copied_byte_for_byte(tmp_path, backlog):
    write_config(backlog, prefix="QA", lastCode=0, gitignored=True)
    latin1 = tmp_path / "latin1.md"
    latin1.write_bytes("# {{CODE}} · año\n".encode("latin-1"))

    result = subprocess.run(
        [str(WRITE_STORY), str(backlog), "new", str(latin1)],
        capture_output=True,
        env={**os.environ, "LC_ALL": "en_US.UTF-8"},
    )

    assert result.returncode == 0, result.stderr
    assert (backlog / "QA-0001-new.md").read_bytes() == "# QA-0001 · año\n".encode("latin-1")


def test_an_invalid_byte_before_the_placeholder_still_finds_it(tmp_path, backlog):
    write_config(backlog, prefix="QA", lastCode=0, gitignored=True)
    odd = tmp_path / "odd.md"
    odd.write_bytes(b"\xe9\xe9 {{CODE}}\n")

    result = subprocess.run(
        [str(WRITE_STORY), str(backlog), "new", str(odd)],
        capture_output=True,
        env={**os.environ, "LC_ALL": "en_US.UTF-8"},
    )

    assert result.returncode == 0, result.stderr
    assert (backlog / "QA-0001-new.md").read_bytes() == b"\xe9\xe9 QA-0001\n"


@pytest.mark.parametrize("last_code", ["99999999999999999999", "9223372036854775807", "1000000000"])
def test_a_counter_too_large_for_shell_arithmetic_is_refused(tmp_path, backlog, last_code):
    config = f'{{"prefix": "QA", "lastCode": {last_code}}}'
    (backlog / ".backlog-config.json").write_text(config)

    result = run(backlog, "new", draft(tmp_path))

    assert result.returncode == 1
    assert story_files(backlog) == []
    assert (backlog / ".backlog-config.json").read_text() == config


def test_leading_zeros_in_the_counter_are_read_as_decimal(tmp_path, backlog):
    (backlog / ".backlog-config.json").write_text('{"prefix": "QA", "lastCode": 0000000012}')

    result = run(backlog, "new", draft(tmp_path))

    assert result.returncode == 0, result.stderr
    assert story_files(backlog) == ["QA-0013-new.md"]
