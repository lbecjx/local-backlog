# local-backlog — a local issue/story tracker for Claude Code, no cloud account needed
# Copyright (C) 2026  lbecjx
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version. See LICENSE for the full text.

# Runs the OpenCode plugin harness (scripts/opencode-plugin.test.sh) from the
# pytest suite, so the plugin's logic is exercised by the repo's one test
# runner instead of only by hand. The harness itself skips without node; this
# mirrors that skip so a node-less environment isn't reported as a failure.

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
HARNESS = REPO_ROOT / "scripts" / "opencode-plugin.test.sh"


def test_opencode_plugin_harness_passes():
    if shutil.which("node") is None:
        pytest.skip("node isn't installed — the OpenCode plugin harness can't run")

    result = subprocess.run(["bash", str(HARNESS)], capture_output=True, text=True)

    assert result.returncode == 0, result.stdout + result.stderr
