# local-backlog — a local issue/story tracker for Claude Code, no cloud account needed
# Copyright (C) 2026  lbecjx
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version. See LICENSE for the full text.

# Shared pytest fixtures: a scratch local-backlog/ project (mirroring the
# real story-file template) and a real idle_server.py instance running
# against it, staged the same way open-backlog.sh actually does (a symlink
# named "backlog" pointing at the real folder) — these tests exercise the
# genuine server process over real HTTP, not a mocked handler, so a passing
# test means the actual script works, not just that its logic reads right.

import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
IDLE_SERVER = REPO_ROOT / "skills" / "open-backlog" / "scripts" / "idle_server.py"


def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


class Scratch:
    """A throwaway local-backlog/ project, one per test (via tmp_path)."""

    def __init__(self, tmp_path):
        self.repo = tmp_path / "repo"
        self.backlog = self.repo / "local-backlog"
        self.backlog.mkdir(parents=True)
        (self.backlog / ".backlog-config.json").write_text(
            json.dumps({"prefix": "QA", "lastCode": 0, "gitignored": True})
        )
        (self.backlog / ".backlog-statuses.json").write_text(
            json.dumps(
                {
                    "statuses": [
                        {"name": "Not Started", "color": "gray"},
                        {"name": "In Progress", "color": "blue"},
                        {"name": "Done", "color": "green"},
                    ]
                }
            )
        )
        (self.backlog / ".backlog-board.json").write_text(json.dumps({"planner": [], "archive": []}))

        self.stage = tmp_path / "stage"
        self.stage.mkdir()
        (self.stage / "backlog").symlink_to(self.backlog)

    def write_story(self, code, status):
        path = self.backlog / f"{code}-story.md"
        path.write_text(
            f"""# {code} · test story

| Field | Value |
|---|---|
| **Code** | {code} |
| **Type** | Task |
| **Priority** | Low |
| **Status** | {status} |
| **Labels** | test |
| **Created** | 2026-01-01 |
| **Updated** | 2026-01-01 |

---

## Description
Test story.

## History
- 2026-01-01: Created with Status "{status}"

---

> Generated for testing.
"""
        )
        return path

    def status_of(self, code):
        text = (self.backlog / f"{code}-story.md").read_text()
        for line in text.splitlines():
            if line.startswith("| **Status**"):
                return line.split("|")[2].strip()
        return None

    def history_of(self, code):
        text = (self.backlog / f"{code}-story.md").read_text()
        return [line for line in text.splitlines() if line.startswith("- ")]

    def board(self):
        return json.loads((self.backlog / ".backlog-board.json").read_text())


@pytest.fixture
def scratch(tmp_path):
    return Scratch(tmp_path)


@pytest.fixture
def server(scratch):
    """Starts the real idle_server.py against the scratch stage dir; yields
    (base_url, scratch). Killed unconditionally on teardown — no state in
    this fixture survives past the test that requested it."""
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, str(IDLE_SERVER), str(port), str(scratch.stage)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    base_url = f"http://localhost:{port}"
    for _ in range(50):
        if proc.poll() is not None:
            raise RuntimeError(f"server exited early:\n{proc.stdout.read()}")
        try:
            urllib.request.urlopen(f"{base_url}/backlog/", timeout=0.2)
            break
        except Exception:
            time.sleep(0.1)
    else:
        proc.kill()
        raise RuntimeError("server never came up")

    try:
        yield base_url, scratch
    finally:
        proc.kill()
        proc.wait(timeout=5)


def post(base_url, path, body, origin="__default__", referer=None):
    """POSTs `body` (a dict, auto-JSON-encoded, or a raw str/bytes for
    malformed-body tests) to `path`. `origin` defaults to a correct,
    matching Origin header; pass None to omit it, or an arbitrary string to
    send a wrong one. Returns (status_code, parsed_json_or_None) — a
    connection reset (the handler thread crashing) surfaces as
    (None, None) rather than raising, so a test can assert on it directly.
    """
    if isinstance(body, str):
        data = body.encode()
    elif isinstance(body, bytes):
        data = body
    else:
        data = json.dumps(body).encode()

    req = urllib.request.Request(f"{base_url}{path}", data=data, method="POST")
    if origin == "__default__":
        req.add_header("Origin", base_url)
    elif origin is not None:
        req.add_header("Origin", origin)
    if referer is not None:
        req.add_header("Referer", referer)

    try:
        resp = urllib.request.urlopen(req, timeout=5)
        return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body_bytes = e.read()
        try:
            return e.code, json.loads(body_bytes)
        except json.JSONDecodeError:
            return e.code, body_bytes.decode(errors="replace")
    except (urllib.error.URLError, ConnectionResetError, ConnectionAbortedError):
        return None, None
