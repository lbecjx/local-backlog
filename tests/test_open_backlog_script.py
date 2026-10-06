# local-backlog — a local issue/story tracker for Claude Code, no cloud account needed
# Copyright (C) 2026  lbecjx
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version. See LICENSE for the full text.

# Tests for open-backlog.sh's resolution reporting and its two additive
# invocation shapes (LB-0017): `--resolve-only` reports what would be opened
# without opening anything, and `--root <path>` opens a specific project
# instead of resolving one from git/pwd. Drives the real script as a
# subprocess; the one test that takes the full open path stubs `open` on
# PATH so no browser is launched, and kills the server it started.

import hashlib
import os
import shutil
import signal
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "skills" / "open-backlog" / "scripts" / "open-backlog.sh"
BASH = shutil.which("bash") or "/bin/bash"

STORY = "# {code} · test\n\n| **Code** | {code} |\n| **Status** | Not Started |\n"


def make_repo(tmp_path, name="proj", stories=("AA-0001",), git=False):
    repo = tmp_path / name
    backlog = repo / "local-backlog"
    backlog.mkdir(parents=True)
    (backlog / ".backlog-config.json").write_text(
        '{"prefix": "AA", "lastCode": 1, "gitignored": true}'
    )
    for code in stories:
        (backlog / f"{code}-story.md").write_text(STORY.format(code=code))
    if git:
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    return repo


def run(args, cwd=None, env=None):
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
    )


def parse(stdout):
    return dict(line.split(":", 1) for line in stdout.splitlines() if ":" in line)


def real(path):
    return os.path.realpath(path)


def git_root(repo):
    return subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], cwd=repo, capture_output=True, text=True
    ).stdout.strip()


def stage_dir(root_string):
    tmpdir = os.environ.get("TMPDIR", "/tmp")
    digest = hashlib.sha1(root_string.encode()).hexdigest()[:12]
    return Path(tmpdir) / "local-backlog-viewer" / digest


def test_resolve_only_reports_project_root_and_stories(tmp_path):
    repo = make_repo(tmp_path, name="proj", stories=("AA-0001", "AA-0002"))

    result = run(["--resolve-only", "--root", str(repo)])

    assert result.returncode == 0
    out = parse(result.stdout)
    assert out["PROJECT"] == "proj"
    assert real(out["ROOT"]) == real(repo)
    assert out["STORIES"] == "2"
    # resolve-only must not report a successful open.
    assert "OPENED" not in out


def test_resolve_only_reports_no_backlog_without_one(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()

    result = run(["--resolve-only", "--root", str(empty)])

    assert result.returncode == 0
    assert result.stdout.strip() == "NO_BACKLOG"


def test_root_bypasses_git_resolution(tmp_path):
    elsewhere = make_repo(tmp_path, name="one", git=True)
    target = make_repo(tmp_path, name="two")

    # cwd is a different git repo than --root names.
    result = run(["--resolve-only", "--root", str(target)], cwd=elsewhere)

    out = parse(result.stdout)
    assert out["PROJECT"] == "two"
    assert real(out["ROOT"]) == real(target)


def test_no_argument_resolves_the_git_root_from_a_subdirectory(tmp_path):
    repo = make_repo(tmp_path, name="gitproj", git=True)
    subdir = repo / "sub"
    subdir.mkdir()

    result = run(["--resolve-only"], cwd=subdir)

    out = parse(result.stdout)
    assert out["PROJECT"] == "gitproj"
    assert real(out["ROOT"]) == real(repo)


def test_unknown_argument_fails_loudly(tmp_path):
    result = run(["--bogus"])

    assert result.returncode == 2
    assert "Unknown argument" in result.stderr


def test_root_without_a_value_fails_loudly(tmp_path):
    result = run(["--root"])

    assert result.returncode == 2
    assert "requires a non-empty path" in result.stderr


def test_root_rejects_an_empty_value(tmp_path):
    result = run(["--root", ""])

    assert result.returncode == 2
    assert "requires a non-empty path" in result.stderr


def test_root_that_does_not_exist_reports_no_backlog(tmp_path):
    result = run(["--resolve-only", "--root", str(tmp_path / "does-not-exist")])

    assert result.returncode == 0
    assert result.stdout.strip() == "NO_BACKLOG"


def test_root_requires_local_backlog_as_a_direct_child(tmp_path):
    # local-backlog/ sits under the parent, not directly under the --root target.
    repo = make_repo(tmp_path, name="parent", stories=("AA-0001",))
    subdir = repo / "sub"
    subdir.mkdir()

    result = run(["--resolve-only", "--root", str(subdir)])

    assert result.stdout.strip() == "NO_BACKLOG"


def test_root_value_that_looks_like_a_flag_is_not_a_cd_option(tmp_path):
    # `cd --` must treat a leading-dash value as a literal path, never as cd's
    # own option — otherwise `--root --` would silently resolve to $HOME.
    result = run(["--resolve-only", "--root", "--"])

    assert result.returncode == 0
    assert result.stdout.strip() == "NO_BACKLOG"


def test_root_single_dash_is_not_resolved_as_oldpwd(tmp_path):
    # `cd -- -` still treats a bare `-` as $OLDPWD, so the script prefixes a
    # non-absolute operand with "./" — a `-` root must not open $OLDPWD's
    # backlog when that directory happens to have one.
    repo = make_repo(tmp_path, name="oldpwd-proj")
    env = dict(os.environ, OLDPWD=str(repo))

    result = subprocess.run(
        [BASH, str(SCRIPT), "--resolve-only", "--root", "-"],
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "NO_BACKLOG"


def test_resolve_only_reports_no_python3_when_python3_is_absent(tmp_path):
    repo = make_repo(tmp_path, name="proj")
    empty_bin = tmp_path / "emptybin"
    empty_bin.mkdir()
    env = dict(os.environ, PATH=str(empty_bin))

    result = subprocess.run(
        [BASH, str(SCRIPT), "--resolve-only", "--root", str(repo)],
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "NO_PYTHON3"


def test_full_open_reports_project_and_root(tmp_path):
    repo = make_repo(tmp_path, name="openproj", git=True)

    # Stub the browser opener so the test never launches a real browser.
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for opener in ("open", "xdg-open"):
        stub = bin_dir / opener
        stub.write_text("#!/bin/sh\nexit 0\n")
        stub.chmod(0o755)
    env = dict(os.environ, PATH=f"{bin_dir}{os.pathsep}{os.environ['PATH']}")

    root = git_root(repo)
    result = run([], cwd=repo, env=env)
    try:
        assert result.returncode == 0
        out = parse(result.stdout)
        assert out["PROJECT"] == "openproj"
        assert real(out["ROOT"]) == real(root)
        assert out["STORIES"] == "1"
        assert int(out["OPENED"]) > 0
    finally:
        pid_file = stage_dir(root) / ".viewer.pid"
        if pid_file.exists():
            pid = int(pid_file.read_text().split(":")[0])
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
