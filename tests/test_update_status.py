# local-backlog — a local issue/story tracker for Claude Code, no cloud account needed
# Copyright (C) 2026  lbecjx
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version. See LICENSE for the full text.

# Dedicated suite for update-status.sh — the only supported way to change a
# story's Status. These classes used to live in tests/test_idle_server.py,
# grown a second home inside a file named after the HTTP server even though
# the script is reachable both from the server's write endpoints and directly
# from the slash command; LB-0016 moved them here so the script has one test
# home, beside the get-zone/set-zone tests in tests/test_update_status_scripts.py.
# Every test drives the real script as a subprocess against a scratch story
# file (or, for the lock/timeout tests, a real process it can stall), not a
# mocked helper.

import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
UPDATE_STATUS = REPO_ROOT / "skills" / "update-status" / "scripts" / "update-status.sh"


class TestUpdateStatusLock:
    def test_lock_directory_is_cleaned_up_after_a_normal_run(self, tmp_path):
        backlog = tmp_path / "local-backlog"
        backlog.mkdir()
        story = backlog / "LK-0001-story.md"
        story.write_text(
            "# LK-0001\n\n| **Status** | Not Started |\n\n---\n## History\n- created\n\n---\n"
        )
        script = UPDATE_STATUS
        result = subprocess.run([str(script), str(story), "Done", "--resolution", "Done"], capture_output=True, text=True)
        assert result.returncode == 0
        assert not (backlog / f"{story.name}.lock").exists()

    STORY = (
        "# LK-0001\n\n| **Status** | Not Started |\n\n---\n## History\n- created\n\n---\n"
    )

    def _story(self, tmp_path, text=None):
        backlog = tmp_path / "local-backlog"
        backlog.mkdir()
        story = backlog / "LK-0001-story.md"
        story.write_text(self.STORY if text is None else text)
        return backlog, story

    @staticmethod
    def _shim_awk(tmp_path, body):
        """A stand-in `awk` first on PATH, so a test can stall or fail the write step."""
        shim_dir = tmp_path / "shim"
        shim_dir.mkdir()
        shim = shim_dir / "awk"
        shim.write_text(f"#!/bin/bash\n{body}\n")
        shim.chmod(0o755)
        scratch_tmp = tmp_path / "tmp"
        scratch_tmp.mkdir()
        return {**os.environ, "PATH": f"{shim_dir}:{os.environ['PATH']}", "TMPDIR": str(scratch_tmp)}

    @staticmethod
    def _names(directory):
        return sorted(p.name for p in directory.iterdir())

    def test_the_stories_file_mode_is_kept(self, tmp_path):
        _, story = self._story(tmp_path)
        story.chmod(0o644)

        result = subprocess.run([str(UPDATE_STATUS), str(story), "In Progress"], capture_output=True, text=True)

        assert result.returncode == 0, result.stderr
        assert story.stat().st_mode & 0o777 == 0o644

    def test_nothing_is_left_behind_after_a_successful_run(self, tmp_path):
        backlog, story = self._story(tmp_path)

        result = subprocess.run([str(UPDATE_STATUS), str(story), "In Progress"], capture_output=True, text=True)

        assert result.returncode == 0, result.stderr
        assert self._names(backlog) == [story.name]

    @pytest.mark.parametrize(
        "args, text, code",
        [
            (["Nope"], None, 2),
            (["In Progress", "--expect", "Done"], None, 3),
            (["In Progress"], "# LK-0001\n\n| **Status** | Not Started |\n", 1),
        ],
        ids=["non-canonical status", "--expect mismatch", "no History section"],
    )
    def test_nothing_is_left_behind_after_a_refused_run(self, tmp_path, args, text, code):
        backlog, story = self._story(tmp_path, text)
        before = story.read_text()

        result = subprocess.run([str(UPDATE_STATUS), str(story), *args], capture_output=True, text=True)

        assert result.returncode == code
        assert story.read_text() == before
        assert self._names(backlog) == [story.name]

    def test_nothing_is_left_behind_after_a_failed_rewrite(self, tmp_path):
        backlog, story = self._story(tmp_path)
        before = story.read_text()
        env = self._shim_awk(tmp_path, "exit 1")

        result = subprocess.run([str(UPDATE_STATUS), str(story), "In Progress"], env=env, capture_output=True, text=True)

        assert result.returncode == 1
        assert "Failed to rewrite" in result.stderr
        assert story.read_text() == before
        assert self._names(backlog) == [story.name]

    def _stalled_run(self, tmp_path, backlog, story, hold):
        """Start an update whose write step reports in, then holds for `hold` seconds."""
        sentinel = tmp_path / "write-step-reached"
        real_awk = shutil.which("awk")
        env = self._shim_awk(tmp_path, f'touch "{sentinel}"\nsleep {hold}\nexec {real_awk} "$@"')
        proc = subprocess.Popen(
            [str(UPDATE_STATUS), str(story), "In Progress"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        deadline = time.monotonic() + 10
        while not sentinel.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert sentinel.exists(), "the run never reached the write step"
        return proc

    def test_an_interrupt_mid_write_leaves_no_lock_or_temp_file(self, tmp_path):
        backlog, story = self._story(tmp_path)
        before = story.read_text()
        proc = self._stalled_run(tmp_path, backlog, story, hold=2)
        try:
            # Mid-write the folder holds the story, the lock directory and the temp
            # file — and the temp file's name is not one a `*.md` glob would match.
            assert len(self._names(backlog)) == 3
            assert list(backlog.glob("*.md")) == [story]
            proc.terminate()
            proc.wait(timeout=10)
        finally:
            if proc.poll() is None:
                proc.kill()

        assert proc.returncode == 143
        assert story.read_text() == before
        assert self._names(backlog) == [story.name]

    def test_a_shared_folder_keeps_the_temp_file_out_of_it(self, tmp_path):
        backlog, story = self._story(tmp_path)
        story.chmod(0o644)
        backlog.chmod(0o775)  # writable by the group: someone else could swap a temp file in it
        proc = self._stalled_run(tmp_path, backlog, story, hold=1)
        try:
            # Only the story and the lock are in the folder; the temp file went to $TMPDIR.
            assert self._names(backlog) == [story.name, f"{story.name}.lock"]
            assert len(self._names(tmp_path / "tmp")) == 1
            assert proc.wait(timeout=10) == 0
        finally:
            if proc.poll() is None:
                proc.kill()

        assert "| **Status** | In Progress |" in story.read_text()
        assert story.stat().st_mode & 0o777 == 0o644
        assert self._names(backlog) == [story.name]
        assert self._names(tmp_path / "tmp") == []


class TestUpdateStatusResolution:
    def _story(self, tmp_path, status="Not Started", resolution="", note=""):
        backlog = tmp_path / "local-backlog"
        backlog.mkdir()
        story = backlog / "RS-0001-story.md"
        story.write_text(
            "# RS-0001 · x\n\n| Field | Value |\n|---|---|\n"
            f"| **Code** | RS-0001 |\n| **Status** | {status} |\n"
            f"| **Resolution** | {resolution} |\n| **Note** | {note} |\n"
            "| **Updated** | 2026-01-01 |\n\n---\n\n"
            "## History\n\n- 2026-01-01T00:00:00Z — Created\n\n---\n"
        )
        return story

    def _run(self, *args):
        script = UPDATE_STATUS
        return subprocess.run([str(script), *args], capture_output=True, text=True)

    def test_done_without_resolution_is_refused(self, tmp_path):
        story = self._story(tmp_path)
        r = self._run(str(story), "Done")
        assert r.returncode == 2
        assert "requires --resolution" in r.stderr
        assert "| **Status** | Not Started |" in story.read_text()  # untouched

    def test_done_with_valid_resolution_and_note_writes_rows(self, tmp_path):
        story = self._story(tmp_path)
        r = self._run(str(story), "Done", "--resolution", "Won't Do", "--note", "deprioritized")
        assert r.returncode == 0
        text = story.read_text()
        assert "| **Status** | Done |" in text
        assert "| **Resolution** | Won't Do |" in text
        assert "| **Note** | deprioritized |" in text

    def test_custom_resolution_rejected(self, tmp_path):
        story = self._story(tmp_path)
        r = self._run(str(story), "Done", "--resolution", "Maybe")
        assert r.returncode == 2
        assert "Maybe" in r.stderr

    def test_leaving_done_clears_rows(self, tmp_path):
        story = self._story(tmp_path, status="Done", resolution="Won't Do", note="old")
        r = self._run(str(story), "In Progress")
        assert r.returncode == 0
        text = story.read_text()
        assert "| **Resolution** |  |" in text
        assert "| **Note** |  |" in text

    def test_resolution_on_non_done_is_rejected(self, tmp_path):
        story = self._story(tmp_path)
        r = self._run(str(story), "In Progress", "--resolution", "Done")
        assert r.returncode == 1

    def test_note_with_a_newline_is_refused_without_touching_the_story(self, tmp_path):
        story = self._story(tmp_path)
        before = story.read_text()
        r = self._run(str(story), "In Progress", "--note", "line1\nline2")
        assert r.returncode == 2
        assert story.read_text() == before

    def test_backslash_in_note_is_preserved_literally(self, tmp_path):
        # awk -v used to run the value through its own escape processing, so a
        # backslash became a newline/tab and split the metadata table.
        story = self._story(tmp_path)
        r = self._run(str(story), "In Progress", "--note", "path C:\\new\\test")
        assert r.returncode == 0
        assert "| **Note** | path C:\\new\\test |" in story.read_text()

    def test_pipe_in_note_is_refused(self, tmp_path):
        story = self._story(tmp_path)
        r = self._run(str(story), "In Progress", "--note", "a|b")
        assert r.returncode == 2

    @pytest.mark.skipif(sys.platform != "darwin", reason="chflags is macOS-specific")
    def test_failed_write_leaves_the_story_unchanged(self, tmp_path):
        # An unwritable target must fail loudly, not report success while the
        # story stays on its old status (and leak the temp file).
        story = self._story(tmp_path)
        before = story.read_text()
        subprocess.run(["chflags", "uchg", str(story)], check=True)
        try:
            r = self._run(str(story), "In Progress")
            assert r.returncode == 1
        finally:
            subprocess.run(["chflags", "nouchg", str(story)], check=True)
        assert story.read_text() == before
        assert sorted(p.name for p in story.parent.iterdir()) == [story.name]

    def test_backfill_fills_an_empty_resolution_without_a_history_line(self, tmp_path):
        # A legacy `Status: Done` story (predating the Resolution field): asking
        # for it with a resolution fills the row — the Status does not change and
        # no History line is invented for a transition that never happened.
        story = self._story(tmp_path, status="Done", resolution="")
        before_history = [line for line in story.read_text().splitlines() if line.startswith("- ")]
        r = self._run(str(story), "Done", "--resolution", "Done")
        assert r.returncode == 0
        text = story.read_text()
        assert "| **Status** | Done |" in text
        assert "| **Resolution** | Done |" in text
        assert [line for line in text.splitlines() if line.startswith("- ")] == before_history

    def test_backfill_is_idempotent_and_never_overwrites_a_resolution(self, tmp_path):
        story = self._story(tmp_path, status="Done", resolution="")
        assert self._run(str(story), "Done", "--resolution", "Done").returncode == 0
        after = story.read_text()
        # Re-running, or asking for a different resolution once one is set,
        # changes nothing.
        assert self._run(str(story), "Done", "--resolution", "Done").returncode == 0
        assert self._run(str(story), "Done", "--resolution", "Won't Do").returncode == 0
        assert story.read_text() == after

    def test_done_without_resolution_and_no_flag_is_still_a_noop(self, tmp_path):
        story = self._story(tmp_path, status="Done", resolution="")
        before = story.read_text()
        r = self._run(str(story), "Done")
        assert r.returncode == 0
        assert story.read_text() == before

    def test_backfill_preserves_an_existing_note(self, tmp_path):
        story = self._story(tmp_path, status="Done", resolution="", note="kept")
        r = self._run(str(story), "Done", "--resolution", "Done")
        assert r.returncode == 0
        text = story.read_text()
        assert "| **Resolution** | Done |" in text
        assert "| **Note** | kept |" in text

    def test_backfill_never_overwrites_an_existing_note(self, tmp_path):
        # The backfill is not a transition, so a note passed with it has nothing
        # to attach to and no History line records the write. Overwriting would
        # destroy the story's current note silently — reachable end to end from
        # /api/board archiving a story that is already Done with an empty
        # Resolution (the archive reason is forwarded as --note).
        story = self._story(tmp_path, status="Done", resolution="", note="original legacy note")
        r = self._run(str(story), "Done", "--resolution", "Won't Do", "--note", "archived because stale")
        assert r.returncode == 0
        text = story.read_text()
        assert "| **Resolution** | Won't Do |" in text
        assert "| **Note** | original legacy note |" in text

    def test_backfill_a_legacy_story_without_resolution_rows(self, tmp_path):
        # The real legacy shape: the story predates the Resolution/Note rows
        # entirely. The write inserts them (filled) rather than failing.
        backlog = tmp_path / "local-backlog"
        backlog.mkdir()
        story = backlog / "LG-0001-story.md"
        story.write_text(
            "# LG-0001 · x\n\n| Field | Value |\n|---|---|\n"
            "| **Code** | LG-0001 |\n| **Status** | Done |\n"
            "| **Updated** | 2026-01-01 |\n\n---\n\n"
            "## History\n\n- 2026-01-01T00:00:00Z — Created\n\n---\n"
        )
        r = self._run(str(story), "Done", "--resolution", "Done")
        assert r.returncode == 0
        text = story.read_text()
        assert "| **Resolution** | Done |" in text
        assert "| **Note** |  |" in text


class TestHistoryLineSegments:
    """The appended `## History` line carries the transition's own Resolution
    and Note — after the new status, in that order, and only when they exist.
    The `Note` row can't hold more than the current one, so this line is what
    keeps an earlier transition's reason readable."""

    def _story(self, tmp_path, status="Not Started", resolution="", note="", after_history="\n---\n"):
        backlog = tmp_path / "local-backlog"
        backlog.mkdir()
        story = backlog / "HS-0001-story.md"
        story.write_text(
            "# HS-0001 · x\n\n| Field | Value |\n|---|---|\n"
            f"| **Code** | HS-0001 |\n| **Status** | {status} |\n"
            f"| **Resolution** | {resolution} |\n| **Note** | {note} |\n"
            "| **Updated** | 2026-01-01 |\n\n---\n\n"
            "## History\n\n- 2026-01-01T00:00:00Z — Created\n"
            f"{after_history}"
        )
        return story

    def _run(self, *args):
        script = UPDATE_STATUS
        return subprocess.run([str(script), *args], capture_output=True, text=True)

    def _last_history_line(self, story):
        return [line for line in story.read_text().splitlines() if line.startswith("- ")][-1]

    def test_done_transition_records_resolution_then_note(self, tmp_path):
        story = self._story(tmp_path)
        r = self._run(str(story), "Done", "--resolution", "Done", "--note", "shipped in PR #14")
        assert r.returncode == 0
        assert re.fullmatch(
            r"- \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z — Status: Not Started → Done"
            r" · Resolution: Done · Note: shipped in PR #14",
            self._last_history_line(story),
        )

    def test_done_transition_with_a_resolution_and_no_note(self, tmp_path):
        # The most common real flow: a human skips the note on a Done move, so
        # only the Resolution segment is present. A regression that dropped or
        # duplicated it when no Note follows would otherwise go unnoticed.
        story = self._story(tmp_path)
        r = self._run(str(story), "Done", "--resolution", "Won't Do")
        assert r.returncode == 0
        assert re.fullmatch(
            r"- \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z — Status: Not Started → Done"
            r" · Resolution: Won't Do",
            self._last_history_line(story),
        )

    def test_non_done_transition_with_a_note_records_only_the_note(self, tmp_path):
        story = self._story(tmp_path)
        r = self._run(str(story), "In Progress", "--note", "waiting on the payments API")
        assert r.returncode == 0
        assert re.fullmatch(
            r"- \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z — Status: Not Started → In Progress"
            r" · Note: waiting on the payments API",
            self._last_history_line(story),
        )

    def test_transition_without_a_note_keeps_the_bare_line(self, tmp_path):
        story = self._story(tmp_path)
        r = self._run(str(story), "In Progress")
        assert r.returncode == 0
        assert re.fullmatch(
            r"- \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z — Status: Not Started → In Progress",
            self._last_history_line(story),
        )

    def test_leaving_done_does_not_leak_the_old_resolution_or_note(self, tmp_path):
        # The story still carries a Resolution and a Note from its Done state;
        # the new line describes only this transition, so neither may reappear
        # on it (they are cleared from the rows instead).
        story = self._story(tmp_path, status="Done", resolution="Won't Do", note="old reason")
        r = self._run(str(story), "In Progress")
        assert r.returncode == 0
        assert re.fullmatch(
            r"- \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z — Status: Done → In Progress",
            self._last_history_line(story),
        )

    def test_a_note_containing_the_segment_marker_is_stored_verbatim(self, tmp_path):
        # A note is free text; the plugin deliberately does not forbid `·` in
        # it (only newlines, CR and `|`). Pin the writer's contract so the
        # viewer's parser is written against a known shape: the text is stored
        # exactly as given, unescaped — hence "split on the FIRST marker".
        story = self._story(tmp_path)
        note = "blocked · Note: not the marker"
        r = self._run(str(story), "Blocked", "--note", note)
        assert r.returncode == 0
        assert self._last_history_line(story).endswith(f" — Status: Not Started → Blocked · Note: {note}")
        assert f"| **Note** | {note} |" in story.read_text()

    def _history_block(self, story):
        """The text of the `## History` section up to the following separator."""
        return story.read_text().split("## History", 1)[1].split("---", 1)[0]

    def test_history_line_lands_inside_the_section_when_no_blank_line_follows(self, tmp_path):
        # The section is followed straight by `---` instead of a blank line. The
        # line must be inserted BEFORE that separator — it used to be appended
        # after it, i.e. outside `## History` entirely.
        story = self._story(tmp_path, after_history="---\n\n> footer\n")
        r = self._run(str(story), "In Progress", "--note", "hello")
        assert r.returncode == 0
        assert " · Note: hello" in self._history_block(story)

    def test_history_line_is_appended_when_the_section_ends_the_file(self, tmp_path):
        # Nothing follows the last entry at all. The line must still land in the
        # section: it used to be dropped while the script printed `Appended: …`
        # and exited 0, and the note rides entirely on this line.
        story = self._story(tmp_path, after_history="")
        r = self._run(str(story), "In Progress", "--note", "hello")
        assert r.returncode == 0
        assert " · Note: hello" in self._history_block(story)
        assert self._last_history_line(story).endswith("— Status: Not Started → In Progress · Note: hello")

    def test_history_line_is_appended_into_a_section_with_no_entries(self, tmp_path):
        # A malformed story whose `## History` has no entry at all (the template
        # always writes a "Created" one). The line must still be written — as the
        # section's first entry — instead of the script reporting `Appended: …`
        # while dropping it, which lost the note with it.
        backlog = tmp_path / "local-backlog"
        backlog.mkdir()
        story = backlog / "HS-0002-story.md"
        story.write_text(
            "# HS-0002 · x\n\n| Field | Value |\n|---|---|\n"
            "| **Code** | HS-0002 |\n| **Status** | Not Started |\n"
            "| **Resolution** |  |\n| **Note** |  |\n"
            "| **Updated** | 2026-01-01 |\n\n---\n\n"
            "## History\n\n---\n"
        )
        r = self._run(str(story), "In Progress", "--note", "hello")
        assert r.returncode == 0
        assert " · Note: hello" in self._history_block(story)

    def test_a_multiline_entry_is_not_split_or_truncated(self, tmp_path):
        # A `## History` entry that wraps onto indented continuation lines: the
        # new transition must land AFTER the whole entry, and no continuation
        # line may be deleted or reordered. Reproduced live on LB-0016 itself —
        # the old awk fired its "block ended" branch on the FIRST continuation
        # line, inserted the new transition there and `next`ed without
        # printing, so that line vanished (and the entry was split in two)
        # while the script still reported `Appended: …` and exited 0.
        backlog = tmp_path / "local-backlog"
        backlog.mkdir()
        story = backlog / "ML-0001-story.md"
        story.write_text(
            "# ML-0001 · x\n\n| Field | Value |\n|---|---|\n"
            "| **Code** | ML-0001 |\n| **Status** | Not Started |\n"
            "| **Resolution** |  |\n| **Note** |  |\n"
            "| **Updated** | 2026-01-01 |\n\n---\n\n"
            "## History\n\n"
            "- 2026-01-01T00:00:00Z — Created\n"
            "- 2026-01-02T00:00:00Z — Scope extended: line one\n"
            "  continuation line two\n"
            "  continuation line three\n"
            "\n---\n\n> footer\n"
        )

        r = self._run(str(story), "In Progress", "--note", "hello")
        assert r.returncode == 0

        block = self._history_block(story).splitlines()
        # Every line of the wrapped entry survives, and in order.
        entry_header = block.index("- 2026-01-02T00:00:00Z — Scope extended: line one")
        assert block[entry_header + 1] == "  continuation line two"
        assert block[entry_header + 2] == "  continuation line three"
        # The transition lands after the whole entry, not inside it.
        transition = next(i for i, line in enumerate(block) if "Status: Not Started → In Progress" in line)
        assert transition == entry_header + 3
        # And the entry's own header line still appears exactly once.
        assert story.read_text().count("- 2026-01-02T00:00:00Z") == 1

    def test_a_terminator_without_a_blank_line_is_not_dropped(self, tmp_path):
        # The same `next`-without-print branch also ate the non-blank line that
        # ends the entry block: a `---` with no blank line before it was
        # replaced by the new history line and vanished. The existing
        # "lands inside the section" test passes either way (its split still
        # finds the note), so this pins the terminator's survival explicitly.
        story = self._story(tmp_path, after_history="---\n\n> footer\n")
        before_separators = story.read_text().count("\n---\n")

        r = self._run(str(story), "In Progress", "--note", "hello")
        assert r.returncode == 0

        text = story.read_text()
        assert " · Note: hello" in self._history_block(story)
        assert "> footer" in text
        assert text.count("\n---\n") == before_separators  # no separator was eaten


# --- LB-0016: gaps the classes above did not cover ---------------------------
#
# Everything above was moved here verbatim from tests/test_idle_server.py; the
# classes below are the coverage AC #1 asked for that the moved tests genuinely
# lacked (no-op, bad-value rejection beyond --note, mode 600, note lifecycle,
# reopening for every resolution, lock contention, and the Step 3 start combo).

GET_ZONE = REPO_ROOT / "skills" / "update-status" / "scripts" / "get-zone.sh"
SET_ZONE = REPO_ROOT / "skills" / "update-status" / "scripts" / "set-zone.sh"
DONE_RESOLUTIONS = ["Done", "Won't Do", "Duplicate", "Cannot Reproduce"]


def _story(backlog, code, status="Not Started", resolution="", note=""):
    path = backlog / f"{code}-story.md"
    path.write_text(
        f"# {code} · x\n\n| Field | Value |\n|---|---|\n"
        f"| **Code** | {code} |\n| **Status** | {status} |\n"
        f"| **Resolution** | {resolution} |\n| **Note** | {note} |\n"
        f"| **Updated** | 2026-01-01 |\n\n---\n\n"
        f"## History\n\n- 2026-01-01T00:00:00Z — Created\n\n---\n"
    )
    return path


def _run(*args):
    return subprocess.run([str(UPDATE_STATUS), *args], capture_output=True, text=True)


def _backlog(tmp_path):
    backlog = tmp_path / "local-backlog"
    backlog.mkdir()
    return backlog


class TestCanonicalValueErrors:
    def test_a_non_canonical_status_lists_the_canonical_statuses(self, tmp_path):
        story = _story(_backlog(tmp_path), "CV-0001")
        before = story.read_text()

        r = _run(str(story), "Nope")

        assert r.returncode == 2
        assert story.read_text() == before  # refused before anything was written
        for name in ("Not Started", "In Progress", "Done", "Blocked"):
            assert f"  - {name}" in r.stderr

    def test_a_non_canonical_resolution_lists_the_canonical_resolutions(self, tmp_path):
        story = _story(_backlog(tmp_path), "CV-0002")
        before = story.read_text()

        r = _run(str(story), "Done", "--resolution", "Maybe")

        assert r.returncode == 2
        assert story.read_text() == before
        for name in DONE_RESOLUTIONS:
            assert f"  - {name}" in r.stderr

    def test_done_without_a_resolution_names_the_flag(self, tmp_path):
        # AC #1 words this as "lists the canonical resolutions", but the script
        # lists them only when a value is present-but-wrong; with the flag
        # absent it names the flag instead. Pin the actual contract rather than
        # the story's paraphrase of it.
        story = _story(_backlog(tmp_path), "CV-0003")
        before = story.read_text()

        r = _run(str(story), "Done")

        assert r.returncode == 2
        assert "--resolution" in r.stderr
        assert story.read_text() == before


class TestBadValueRejection:
    def test_a_pipe_in_the_resolution_is_refused_before_writing(self, tmp_path):
        story = _story(_backlog(tmp_path), "BV-0001")
        before = story.read_text()

        r = _run(str(story), "Done", "--resolution", "Do|ne")

        assert r.returncode == 2
        assert story.read_text() == before

    def test_a_newline_in_the_resolution_is_refused_before_writing(self, tmp_path):
        story = _story(_backlog(tmp_path), "BV-0002")
        before = story.read_text()

        r = _run(str(story), "Done", "--resolution", "Done\nWon't Do")

        assert r.returncode == 2
        assert story.read_text() == before

    def test_a_pipe_in_the_status_is_refused_before_writing(self, tmp_path):
        story = _story(_backlog(tmp_path), "BV-0003")
        before = story.read_text()

        r = _run(str(story), "In|Progress")

        assert r.returncode == 2
        assert story.read_text() == before


class TestNoOpAndFileMode:
    def test_noop_reports_nothing_to_do_and_leaves_the_file_untouched(self, tmp_path):
        story = _story(_backlog(tmp_path), "NO-0001", status="In Progress")
        before = story.read_text()

        r = _run(str(story), "In Progress")

        assert r.returncode == 0
        assert "nothing to do" in r.stdout
        assert story.read_text() == before

    def test_a_600_story_keeps_its_mode(self, tmp_path):
        # The mode-preservation regression was only ever pinned at 0644; the
        # story files this plugin touches in the wild are often 0600.
        story = _story(_backlog(tmp_path), "NO-0002")
        story.chmod(0o600)

        r = _run(str(story), "In Progress")

        assert r.returncode == 0
        assert story.stat().st_mode & 0o777 == 0o600


class TestNoteLifecycle:
    def test_the_note_row_holds_only_the_latest_transition_note(self, tmp_path):
        story = _story(_backlog(tmp_path), "NL-0001")

        assert _run(str(story), "In Progress", "--note", "first").returncode == 0
        assert _run(str(story), "Blocked", "--note", "second").returncode == 0

        assert "| **Note** | second |" in story.read_text()

    def test_each_transitions_note_survives_on_its_own_history_line(self, tmp_path):
        # The single Note row cannot hold more than the current one, so the
        # History line is the only place an earlier transition's reason stays
        # attached to that transition.
        story = _story(_backlog(tmp_path), "NL-0002")

        assert _run(str(story), "In Progress", "--note", "first").returncode == 0
        assert _run(str(story), "Blocked", "--note", "second").returncode == 0

        lines = [line for line in story.read_text().splitlines() if line.startswith("- ")]
        assert any(line.endswith("Status: Not Started → In Progress · Note: first") for line in lines)
        assert any(line.endswith("Status: In Progress → Blocked · Note: second") for line in lines)


class TestReopeningClearsRows:
    @pytest.mark.parametrize("resolution", DONE_RESOLUTIONS)
    def test_leaving_done_clears_both_rows_for_every_resolution(self, tmp_path, resolution):
        # The bulk-reopen incident that started this story relied on exactly
        # this: moving out of Done must clear Resolution and Note no matter
        # what they held.
        story = _story(_backlog(tmp_path), "RO-0001", status="Done", resolution=resolution, note="closed earlier")
        before = story.read_text()
        assert f"| **Resolution** | {resolution} |" in before
        assert "| **Note** | closed earlier |" in before

        r = _run(str(story), "Not Started")

        assert r.returncode == 0
        text = story.read_text()
        assert "| **Resolution** |  |" in text
        assert "| **Note** |  |" in text


class TestLockContention:
    def test_a_stale_lock_times_out_cleanly_without_touching_the_file(self, tmp_path):
        # The lock is a mkdir; a leftover one from a crashed run must make the
        # next update wait out its timeout and fail loudly — never hang forever
        # and never write through the lock.
        story = _story(_backlog(tmp_path), "LK-0001")
        before = story.read_text()
        lock = story.parent / f"{story.name}.lock"
        lock.mkdir()
        try:
            r = _run(str(story), "In Progress")
        finally:
            lock.rmdir()

        assert r.returncode == 1
        assert "another update may be stuck" in r.stderr
        assert story.read_text() == before

    def test_a_lock_released_during_the_wait_lets_the_update_through(self, tmp_path):
        story = _story(_backlog(tmp_path), "LK-0002")
        lock = story.parent / f"{story.name}.lock"
        lock.mkdir()
        proc = subprocess.Popen(
            [str(UPDATE_STATUS), str(story), "In Progress"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            time.sleep(0.3)  # let the run enter its retry loop
            lock.rmdir()
            out, err = proc.communicate(timeout=15)
        finally:
            if proc.poll() is None:
                proc.kill()

        assert proc.returncode == 0, err
        assert "| **Status** | In Progress |" in story.read_text()


class TestStartSetupCombo:
    """Step 3 of the skill applies update-status.sh and set-zone.sh together as
    one logical "start setup". Cover the combo, not just each script alone."""

    def test_status_and_zone_together_start_the_story(self, tmp_path):
        story = _story(_backlog(tmp_path), "SS-0001")

        assert _run(str(story), "In Progress").returncode == 0
        zone = subprocess.run([str(SET_ZONE), str(story), "planner"], capture_output=True, text=True)

        assert zone.returncode == 0, zone.stderr
        assert "| **Status** | In Progress |" in story.read_text()
        got = subprocess.run([str(GET_ZONE), str(story)], capture_output=True, text=True)
        assert got.stdout.strip() == "planner"

    def test_status_only_leaves_the_zone_untouched(self, tmp_path):
        story = _story(_backlog(tmp_path), "SS-0002")

        assert _run(str(story), "In Progress").returncode == 0

        got = subprocess.run([str(GET_ZONE), str(story)], capture_output=True, text=True)
        assert got.stdout.strip() == "backlog"

    def test_zone_only_leaves_the_status_untouched(self, tmp_path):
        story = _story(_backlog(tmp_path), "SS-0003")

        zone = subprocess.run([str(SET_ZONE), str(story), "planner"], capture_output=True, text=True)

        assert zone.returncode == 0, zone.stderr
        assert "| **Status** | Not Started |" in story.read_text()


class TestArchivedStoryIsFrozen:
    """Part C (AC #6): an archived story accepts no change at all except
    unarchive. Archiving is the human's explicit action and is never performed
    by a status change in either direction."""

    def _archived(self, tmp_path, code="AR-0001", status="Done"):
        story = _story(_backlog(tmp_path), code, status=status)
        z = subprocess.run([str(SET_ZONE), str(story), "archive"], capture_output=True, text=True)
        assert z.returncode == 0, z.stderr
        return story

    @pytest.mark.parametrize("target", ["Not Started", "In Progress", "Done", "Blocked"])
    def test_every_status_change_is_refused_byte_identically(self, tmp_path, target):
        story = self._archived(tmp_path)
        before = story.read_text()

        args = [str(story), target]
        if target == "Done":
            args += ["--resolution", "Done"]
        r = _run(*args)

        assert r.returncode == 1
        assert "archived" in r.stderr
        assert "unarchive" in r.stderr
        assert story.read_text() == before

    def test_a_noop_repeat_of_the_current_status_is_also_refused(self, tmp_path):
        # Even asking for the status it is already at is a change attempt on a
        # frozen story — refused, not reported as "nothing to do".
        story = self._archived(tmp_path)  # Status is Done
        before = story.read_text()

        r = _run(str(story), "Done", "--resolution", "Done")

        assert r.returncode == 1
        assert story.read_text() == before

    def test_get_zone_still_reports_archive(self, tmp_path):
        story = self._archived(tmp_path)

        got = subprocess.run([str(GET_ZONE), str(story)], capture_output=True, text=True)

        assert got.stdout.strip() == "archive"

    def test_unarchive_changes_only_the_zone(self, tmp_path):
        story = self._archived(tmp_path)  # Status is Done

        r = subprocess.run([str(SET_ZONE), str(story), "planner"], capture_output=True, text=True)

        assert r.returncode == 0, r.stderr
        text = story.read_text()
        assert "| **Zone** | Planner |" in text
        assert "| **Status** | Done |" in text  # the unarchive does not touch Status

    def test_a_status_change_succeeds_after_unarchiving(self, tmp_path):
        story = self._archived(tmp_path)  # Status is Done
        u = subprocess.run([str(SET_ZONE), str(story), "backlog"], capture_output=True, text=True)
        assert u.returncode == 0, u.stderr

        r = _run(str(story), "Not Started")

        assert r.returncode == 0, r.stderr
        assert "| **Status** | Not Started |" in story.read_text()

    def test_archiving_a_not_yet_archived_story_still_works(self, tmp_path):
        # The freeze must not block the archive action itself: it runs the
        # Status→Done write BEFORE the zone write, so the story is not archived
        # yet at that moment.
        story = _story(_backlog(tmp_path), "AR-0002")

        assert _run(str(story), "Done", "--resolution", "Done").returncode == 0
        z = subprocess.run([str(SET_ZONE), str(story), "archive"], capture_output=True, text=True)

        assert z.returncode == 0, z.stderr
        assert "| **Zone** | Archive |" in story.read_text()

    @pytest.mark.parametrize("casing", ["archive", "ARCHIVE", "ArChIvE"])
    def test_a_case_variant_archive_zone_is_still_frozen(self, tmp_path, casing):
        # All three Zone readers (this script, get-zone.sh, idle_server.py)
        # normalize case, so any casing of `archive` freezes the story. A
        # hand-edited lowercase row must not slip a change through the CLI while
        # the HTTP path refuses it.
        story = _story(_backlog(tmp_path), "AR-0003", status="Done")
        story.write_text(story.read_text() + f"| **Zone** | {casing} |\n")
        before = story.read_text()

        r = _run(str(story), "In Progress")

        assert r.returncode == 1
        assert "archived" in r.stderr
        assert story.read_text() == before

    @pytest.mark.parametrize("row", [
        "| **Zone** |Archive |",
        "| **Zone** | Archive|",
        "| **Zone** |Archive|",
        "| **Zone** |  Archive  |",
    ])
    def test_space_variants_the_readers_accept_are_frozen(self, tmp_path, row):
        # The shell readers accept these rows as `archive` (the grep is a prefix
        # match; the sed tolerates spaces around the value), so the guard must
        # freeze them. A row shape no reader recognizes is a separate case below.
        story = _story(_backlog(tmp_path), "AR-0005", status="Done")
        story.write_text(story.read_text() + row + "\n")
        before = story.read_text()

        r = _run(str(story), "In Progress")

        assert r.returncode == 1
        assert "archived" in r.stderr
        assert story.read_text() == before

    def test_a_row_shape_no_reader_recognizes_is_not_frozen(self, tmp_path):
        # `|**Zone**| Archive |` (no space around `**Zone**`) is not the
        # canonical row shape: the grep and the server regex both miss it, so it
        # reads as `backlog` everywhere and the change is allowed — consistent
        # (if lenient), never archived on one side and not the other.
        story = _story(_backlog(tmp_path), "AR-0006", status="Done")
        story.write_text(story.read_text() + "|**Zone**| Archive |\n")

        r = _run(str(story), "In Progress")

        assert r.returncode == 0, r.stderr
        assert "| **Status** | In Progress |" in story.read_text()

    def test_a_tab_delimited_zone_row_is_not_frozen_on_either_side(self, tmp_path):
        # The shell's sed strips ASCII spaces only, so a tab (or NBSP) next to
        # the value is unrecognized by get-zone.sh and by the CLI guard — and it
        # must be unrecognized by the server guard too, or HTTP would freeze a
        # story the CLI would happily change.
        story = _story(_backlog(tmp_path), "AR-0007", status="Done")
        story.write_text(story.read_text() + "| **Zone** |\tArchive\t|\n")

        r = _run(str(story), "In Progress")

        assert r.returncode == 0, r.stderr
        assert "| **Status** | In Progress |" in story.read_text()


class TestTransitionBookkeeping:
    def test_a_normal_transition_rewrites_the_updated_row(self, tmp_path):
        story = _story(_backlog(tmp_path), "TB-0001")

        r = _run(str(story), "In Progress")

        assert r.returncode == 0
        text = story.read_text()
        assert "| **Updated** | 2026-01-01 |" not in text
        assert re.search(r"\| \*\*Updated\*\* \| \d{4}-\d{2}-\d{2} \|", text)

    def test_expect_matching_the_current_status_applies(self, tmp_path):
        # The compare-and-swap's happy path — only the mismatch (exit 3) was
        # asserted before.
        story = _story(_backlog(tmp_path), "TB-0002")

        r = _run(str(story), "In Progress", "--expect", "Not Started")

        assert r.returncode == 0, r.stderr
        assert "| **Status** | In Progress |" in story.read_text()


class TestHistorySectionGuard:
    def test_a_missing_history_section_points_at_the_template(self, tmp_path):
        backlog = _backlog(tmp_path)
        story = backlog / "NH-0001-story.md"
        story.write_text(
            "# NH-0001 · x\n\n| Field | Value |\n|---|---|\n"
            "| **Code** | NH-0001 |\n| **Status** | Not Started |\n"
            "| **Resolution** |  |\n| **Note** |  |\n"
            "| **Updated** | 2026-01-01 |\n\n---\n\n## Description\n\nno history here.\n"
        )
        before = story.read_text()

        r = _run(str(story), "In Progress")

        assert r.returncode == 1
        assert "skills/create-story/references/template.md" in r.stderr
        assert story.read_text() == before
