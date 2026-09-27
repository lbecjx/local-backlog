# local-backlog — a local issue/story tracker for Claude Code, no cloud account needed
# Copyright (C) 2026  lbecjx
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version. See LICENSE for the full text.

# Formalizes the manual QA pass run against Task Group 1 (local-backlog's
# write endpoints) into a repeatable suite. Each test drives the real
# idle_server.py process over real HTTP — see conftest.py's `server`
# fixture — the same way a browser client (or curl, during that manual
# pass) actually would, not a mocked handler standing in for it.

import socket
import subprocess
import sys
import threading
import time

import pytest

from conftest import post, IDLE_SERVER


class TestStatusEndpoint:
    def test_valid_status_change(self, server):
        base_url, scratch = server
        scratch.write_story("QA-0001", "Not Started")
        status, body = post(base_url, "/api/status", {"code": "QA-0001", "status": "In Progress"})
        assert status == 200
        assert scratch.status_of("QA-0001") == "In Progress"

    def test_status_change_to_same_value_is_a_noop(self, server):
        base_url, scratch = server
        scratch.write_story("QA-0001", "In Progress")
        status, body = post(base_url, "/api/status", {"code": "QA-0001", "status": "In Progress"})
        assert status == 200
        assert "nothing to do" in body["result"]

    def test_unrecognized_status_is_400_not_500(self, server):
        base_url, scratch = server
        scratch.write_story("QA-0001", "Not Started")
        status, body = post(base_url, "/api/status", {"code": "QA-0001", "status": "Bogus"})
        assert status == 400
        assert "Bogus" in body["error"]
        assert scratch.status_of("QA-0001") == "Not Started"  # untouched

    def test_missing_status_field(self, server):
        base_url, scratch = server
        scratch.write_story("QA-0001", "Not Started")
        status, body = post(base_url, "/api/status", {"code": "QA-0001"})
        assert status == 400

    def test_missing_code_field(self, server):
        base_url, _ = server
        status, body = post(base_url, "/api/status", {"status": "Done"})
        assert status == 400

    def test_code_with_no_matching_file(self, server):
        base_url, _ = server
        status, body = post(base_url, "/api/status", {"code": "QA-9999", "status": "Done"})
        assert status == 404

    def test_non_string_code_returns_clean_400_not_a_crash(self, server):
        base_url, scratch = server
        scratch.write_story("QA-0001", "Not Started")
        for bad_code in (123, None, ["QA-0001"]):
            status, body = post(base_url, "/api/status", {"code": bad_code, "status": "Done"})
            assert status == 400, f"code={bad_code!r} should 400 cleanly, got {status}"

    def test_non_string_status_returns_clean_400_not_a_crash(self, server):
        base_url, scratch = server
        scratch.write_story("QA-0001", "Not Started")
        status, body = post(base_url, "/api/status", {"code": "QA-0001", "status": 123})
        assert status == 400

    def test_status_to_done_requires_a_resolution(self, server):
        base_url, scratch = server
        scratch.write_story("QA-0001", "In Progress")
        status, body = post(base_url, "/api/status", {"code": "QA-0001", "status": "Done"})
        assert status == 400
        assert scratch.status_of("QA-0001") == "In Progress"  # untouched

    def test_status_to_done_with_valid_resolution_and_note_writes_rows(self, server):
        base_url, scratch = server
        scratch.write_story("QA-0001", "In Progress")
        status, body = post(
            base_url, "/api/status", {"code": "QA-0001", "status": "Done", "resolution": "Done", "note": "shipped"}
        )
        assert status == 200
        assert scratch.status_of("QA-0001") == "Done"
        assert scratch.field("QA-0001", "Resolution") == "Done"
        assert scratch.field("QA-0001", "Note") == "shipped"

    def test_status_to_done_with_custom_resolution_is_400(self, server):
        base_url, scratch = server
        scratch.write_story("QA-0001", "In Progress")
        status, body = post(base_url, "/api/status", {"code": "QA-0001", "status": "Done", "resolution": "Maybe"})
        assert status == 400
        assert scratch.status_of("QA-0001") == "In Progress"  # untouched

    def test_resolution_on_a_non_done_target_is_400(self, server):
        base_url, scratch = server
        scratch.write_story("QA-0001", "Not Started")
        status, body = post(
            base_url, "/api/status", {"code": "QA-0001", "status": "In Progress", "resolution": "Done"}
        )
        assert status == 400
        assert scratch.status_of("QA-0001") == "Not Started"  # untouched

    def test_note_is_recorded_on_a_non_done_transition(self, server):
        base_url, scratch = server
        scratch.write_story("QA-0001", "Not Started")
        status, body = post(base_url, "/api/status", {"code": "QA-0001", "status": "In Progress", "note": "starting"})
        assert status == 200
        assert scratch.status_of("QA-0001") == "In Progress"
        assert scratch.field("QA-0001", "Note") == "starting"

    def test_non_string_note_returns_clean_400(self, server):
        base_url, scratch = server
        scratch.write_story("QA-0001", "Not Started")
        status, body = post(base_url, "/api/status", {"code": "QA-0001", "status": "In Progress", "note": 123})
        assert status == 400

    def test_non_object_json_body_returns_clean_400(self, server):
        # Valid JSON that isn't an object used to reach payload.get() and crash
        # the handler thread (connection reset, no response) instead of a 400.
        base_url, scratch = server
        scratch.write_story("QA-0001", "Not Started")
        for body in ("[]", "null", "5", '"x"', "true"):
            status, resp = post(base_url, "/api/status", body)
            assert status == 400, f"body={body!r} should 400 cleanly, got {status}"

    def test_note_with_a_newline_is_rejected_and_story_untouched(self, server):
        # A raw newline in the note used to make update-status.sh's awk fail
        # and truncate the story file to 0 bytes while reporting success.
        base_url, scratch = server
        scratch.write_story("QA-0001", "Not Started")
        status, body = post(
            base_url, "/api/status", {"code": "QA-0001", "status": "In Progress", "note": "a\nb"}
        )
        assert status == 400
        assert scratch.status_of("QA-0001") == "Not Started"
        assert not scratch.field("QA-0001", "Note")

    def test_note_with_a_pipe_is_rejected(self, server):
        base_url, scratch = server
        scratch.write_story("QA-0001", "Not Started")
        status, body = post(
            base_url, "/api/status", {"code": "QA-0001", "status": "In Progress", "note": "a|b"}
        )
        assert status == 400
        assert scratch.status_of("QA-0001") == "Not Started"


class TestBoardEndpointZoneTransitions:
    def test_move_to_planner(self, server):
        base_url, scratch = server
        scratch.write_story("QA-0001", "Not Started")
        status, body = post(base_url, "/api/board", {"code": "QA-0001", "zone": "planner"})
        assert status == 200
        assert scratch.board()["planner"] == ["QA-0001"]

    def test_archive_without_resolution_is_rejected(self, server):
        base_url, scratch = server
        scratch.write_story("QA-0001", "Not Started")
        status, body = post(base_url, "/api/board", {"code": "QA-0001", "zone": "archive"})
        assert status == 400

    def test_archive_sets_status_done_ac9(self, server):
        base_url, scratch = server
        scratch.write_story("QA-0001", "Not Started")
        status, body = post(base_url, "/api/board", {"code": "QA-0001", "zone": "archive", "resolution": "Done"})
        assert status == 200
        assert scratch.status_of("QA-0001") == "Done"
        archive = scratch.board()["archive"]
        assert archive == [{"code": "QA-0001"}]

    def test_archive_with_wont_do_maps_reason_to_story_note(self, server):
        base_url, scratch = server
        scratch.write_story("QA-0001", "In Progress")
        status, body = post(
            base_url,
            "/api/board",
            {"code": "QA-0001", "zone": "archive", "resolution": "Won't Do", "reason": "deprioritized"},
        )
        assert status == 200
        assert scratch.status_of("QA-0001") == "Done"
        # The board carries only the code; the resolution and the free-text
        # (the viewer's 'reason') belong to the story itself.
        assert scratch.board()["archive"] == [{"code": "QA-0001"}]
        assert scratch.field("QA-0001", "Resolution") == "Won't Do"
        assert scratch.field("QA-0001", "Note") == "deprioritized"

    def test_archive_accepts_every_canonical_resolution(self, server):
        # AC #14: the resolution is validated against the story model, not the
        # old hardcoded ("Done", "Won't Do") tuple, so the rest of the
        # canonical set is accepted too.
        base_url, scratch = server
        scratch.write_story("QA-0001", "Not Started")
        status, body = post(
            base_url, "/api/board", {"code": "QA-0001", "zone": "archive", "resolution": "Duplicate"}
        )
        assert status == 200
        assert scratch.field("QA-0001", "Resolution") == "Duplicate"

    def test_archiving_an_already_done_story_is_a_status_noop(self, server):
        base_url, scratch = server
        scratch.write_story("QA-0001", "Done")
        status, body = post(base_url, "/api/board", {"code": "QA-0001", "zone": "archive", "resolution": "Done"})
        assert status == 200
        assert scratch.status_of("QA-0001") == "Done"

    def test_planner_to_backlog(self, server):
        base_url, scratch = server
        scratch.write_story("QA-0001", "Not Started")
        post(base_url, "/api/board", {"code": "QA-0001", "zone": "planner"})
        status, body = post(base_url, "/api/board", {"code": "QA-0001", "zone": "backlog"})
        assert status == 200
        assert scratch.board()["planner"] == []

    def test_precedence_archive_wins_over_planner_ac10(self, server):
        base_url, scratch = server
        scratch.write_story("QA-0001", "Not Started")
        post(base_url, "/api/board", {"code": "QA-0001", "zone": "planner"})
        status, body = post(base_url, "/api/board", {"code": "QA-0001", "zone": "archive", "resolution": "Done"})
        assert status == 200
        board = scratch.board()
        assert "QA-0001" not in board["planner"]
        assert any(e["code"] == "QA-0001" for e in board["archive"])

    def test_invalid_zone_rejected(self, server):
        base_url, scratch = server
        scratch.write_story("QA-0001", "Not Started")
        status, body = post(base_url, "/api/board", {"code": "QA-0001", "zone": "bogus"})
        assert status == 400

    def test_invalid_resolution_rejected(self, server):
        base_url, scratch = server
        scratch.write_story("QA-0001", "Not Started")
        status, body = post(base_url, "/api/board", {"code": "QA-0001", "zone": "archive", "resolution": "Maybe"})
        assert status == 400

    def test_non_string_resolution_on_non_archive_zone_returns_clean_400(self, server):
        # Regression for a gap found by two independent review passes:
        # `resolution` was only type-checked when zone == "archive".
        base_url, scratch = server
        scratch.write_story("QA-0001", "Not Started")
        status, body = post(base_url, "/api/board", {"code": "QA-0001", "zone": "planner", "resolution": 123})
        assert status == 400

    def test_blank_reason_allowed(self, server):
        base_url, scratch = server
        scratch.write_story("QA-0001", "Not Started")
        status, body = post(
            base_url, "/api/board", {"code": "QA-0001", "zone": "archive", "resolution": "Done", "reason": ""}
        )
        assert status == 200

    def test_ac10_no_code_in_two_zones_at_once(self, server):
        base_url, scratch = server
        for code in ("QA-0001", "QA-0002", "QA-0003"):
            scratch.write_story(code, "Not Started")
        post(base_url, "/api/board", {"code": "QA-0001", "zone": "planner"})
        post(base_url, "/api/board", {"code": "QA-0002", "zone": "archive", "resolution": "Done"})
        post(base_url, "/api/board", {"code": "QA-0003", "zone": "planner"})
        post(base_url, "/api/board", {"code": "QA-0003", "zone": "archive", "resolution": "Done"})
        board = scratch.board()
        planner = set(board["planner"])
        archive = {e["code"] for e in board["archive"]}
        assert not (planner & archive)


class TestSecurityAndAuth:
    def test_missing_origin_and_referer_is_403(self, server):
        base_url, scratch = server
        scratch.write_story("QA-0001", "Not Started")
        status, body = post(base_url, "/api/status", {"code": "QA-0001", "status": "Done"}, origin=None)
        assert status == 403

    def test_wrong_origin_is_403(self, server):
        base_url, scratch = server
        scratch.write_story("QA-0001", "Not Started")
        status, body = post(
            base_url, "/api/status", {"code": "QA-0001", "status": "Done"}, origin="http://evil.example.com"
        )
        assert status == 403

    def test_referer_fallback_accepted_when_origin_absent(self, server):
        base_url, scratch = server
        scratch.write_story("QA-0001", "Not Started")
        status, body = post(
            base_url, "/api/status", {"code": "QA-0001", "status": "In Progress"}, origin=None, referer=base_url + "/"
        )
        assert status == 200


class TestInputRobustness:
    def test_malformed_json_body(self, server):
        base_url, _ = server
        status, body = post(base_url, "/api/status", "not json{")
        assert status == 400

    def test_invalid_utf8_body_returns_clean_400(self, server):
        # UnicodeDecodeError is a sibling of JSONDecodeError, not a subclass —
        # catching only the latter let a raw bad byte crash the handler thread.
        base_url, _ = server
        status, body = post(base_url, "/api/status", b"\xff")
        assert status == 400

    def test_nul_byte_in_a_field_returns_clean_400(self, server):
        # A NUL can't survive execve — it used to crash the handler thread.
        base_url, scratch = server
        scratch.write_story("QA-0001", "Not Started")
        for payload in (
            {"code": "QA-0001", "status": "In Progress", "note": "a\u0000b"},
            {"code": "QA-0001", "status": "In Progress\u0000"},
        ):
            status, body = post(base_url, "/api/status", payload)
            assert status == 400, f"payload={payload!r} should 400 cleanly, got {status}"
        assert scratch.status_of("QA-0001") == "Not Started"

    def test_malformed_content_length_returns_clean_400(self, server):
        # int() on a non-numeric Content-Length used to raise, and a negative
        # one made rfile.read(-1) hang. Sent raw — urllib always sets a correct
        # Content-Length.
        base_url, scratch = server
        scratch.write_story("QA-0001", "Not Started")
        port = int(base_url.rsplit(":", 1)[1])
        with socket.create_connection(("localhost", port), timeout=5) as sock:
            sock.sendall(
                (
                    "POST /api/status HTTP/1.1\r\n"
                    f"Host: localhost:{port}\r\n"
                    f"Origin: {base_url}\r\n"
                    "Content-Length: abc\r\n"
                    "Connection: close\r\n\r\n"
                ).encode()
            )
            first_line = sock.recv(4096).split(b"\r\n", 1)[0]
        assert b" 400 " in first_line

    def test_ambiguous_code_rejected_without_touching_anything(self, server):
        base_url, scratch = server
        scratch.write_story("QA-0001", "Not Started")
        (scratch.backlog / "QA-0001-duplicate.md").write_text((scratch.backlog / "QA-0001-story.md").read_text())
        status, body = post(base_url, "/api/status", {"code": "QA-0001", "status": "Done"})
        assert status == 500
        assert scratch.status_of("QA-0001") == "Not Started"

    def test_unknown_endpoint_is_404_even_without_a_valid_code(self, server):
        base_url, _ = server
        status, body = post(base_url, "/api/bogus", {})
        assert status == 404


class TestArchiveRollback:
    def test_rollback_restores_actual_prior_status_on_board_write_failure(self, server):
        base_url, scratch = server
        scratch.write_story("QA-0001", "In Progress")
        (scratch.backlog / ".backlog-board.json").write_text("{corrupt")
        status, body = post(base_url, "/api/board", {"code": "QA-0001", "zone": "archive", "resolution": "Done"})
        assert status == 500
        assert "rolled back" in body["error"]
        assert scratch.status_of("QA-0001") == "In Progress"

    def test_unrecognized_status_refused_before_touching_anything(self, server):
        # Round-2 Finding A: archiving a story whose Status isn't in the
        # closed list must refuse up front (409), not attempt the Done
        # transition and risk a rollback that fails the same check.
        base_url, scratch = server
        path = scratch.write_story("QA-0001", "Not Started")
        path.write_text(path.read_text().replace("Not Started", "LegacyWeird"))
        status, body = post(base_url, "/api/board", {"code": "QA-0001", "zone": "archive", "resolution": "Done"})
        assert status == 409
        assert scratch.status_of("QA-0001") == "LegacyWeird"

    def test_concurrent_status_write_survives_a_failed_archive_rollback(self, server, monkeypatch):
        # The race this whole mechanism exists to close: a concurrent
        # /api/status write landing during an archive attempt must never be
        # silently discarded by that archive's own rollback, regardless of
        # whether it landed before or after the archive's own Done write.
        base_url, scratch = server
        scratch.write_story("QA-0001", "In Progress")
        (scratch.backlog / ".backlog-board.json").write_text("{corrupt")

        results = {}

        def do_archive():
            results["archive"] = post(base_url, "/api/board", {"code": "QA-0001", "zone": "archive", "resolution": "Done"})

        t = threading.Thread(target=do_archive)
        t.start()
        time.sleep(0.05)  # let the archive request start ahead of this one
        results["status"] = post(base_url, "/api/status", {"code": "QA-0001", "status": "Not Started"})
        t.join(timeout=10)

        assert results["status"][0] == 200
        # Whichever way the race actually landed, the concurrent write must
        # be the one still standing — never silently reverted to a value
        # from before either request began.
        assert scratch.status_of("QA-0001") == "Not Started"


class TestUpdateStatusLock:
    def test_lock_directory_is_cleaned_up_after_a_normal_run(self, tmp_path):
        backlog = tmp_path / "local-backlog"
        backlog.mkdir()
        story = backlog / "LK-0001-story.md"
        story.write_text(
            "# LK-0001\n\n| **Status** | Not Started |\n\n---\n## History\n- created\n\n---\n"
        )
        script = IDLE_SERVER.parent.parent.parent / "update-status" / "scripts" / "update-status.sh"
        result = subprocess.run([str(script), str(story), "Done", "--resolution", "Done"], capture_output=True, text=True)
        assert result.returncode == 0
        assert not (backlog / f"{story.name}.lock").exists()


class TestServerConfiguration:
    def test_accept_backlog_absorbs_the_viewer_startup_burst(self):
        # Import idle_server.py directly (it's import-safe: no argv access and
        # no server start at import) and assert its accept backlog comfortably
        # exceeds the viewer's ~11-connection startup burst. The stdlib default
        # request_queue_size is 5, which that burst overflowed under load.
        import importlib.util

        spec = importlib.util.spec_from_file_location("idle_server", str(IDLE_SERVER))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        assert module.Server.request_queue_size >= 64


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
        script = IDLE_SERVER.parent.parent.parent / "update-status" / "scripts" / "update-status.sh"
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
