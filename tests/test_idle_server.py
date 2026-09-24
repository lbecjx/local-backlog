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

import json
import subprocess
import sys
import threading
import time

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
        status, body = post(base_url, "/api/status", {"code": "QA-0001", "status": "Blocked"})
        assert status == 400
        assert "Blocked" in body["error"]
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
        assert archive == [{"code": "QA-0001", "resolution": "Done", "reason": ""}]

    def test_archive_with_wont_do_and_reason(self, server):
        base_url, scratch = server
        scratch.write_story("QA-0001", "In Progress")
        status, body = post(
            base_url,
            "/api/board",
            {"code": "QA-0001", "zone": "archive", "resolution": "Won't Do", "reason": "deprioritized"},
        )
        assert status == 200
        assert scratch.status_of("QA-0001") == "Done"
        entry = scratch.board()["archive"][0]
        assert entry["resolution"] == "Won't Do"
        assert entry["reason"] == "deprioritized"

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
            base_url, "/api/status", {"code": "QA-0001", "status": "Done"}, origin=None, referer=base_url + "/"
        )
        assert status == 200


class TestInputRobustness:
    def test_malformed_json_body(self, server):
        base_url, _ = server
        status, body = post(base_url, "/api/status", "not json{")
        assert status == 400

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
        (backlog / ".backlog-statuses.json").write_text(
            json.dumps({"statuses": [{"name": "Not Started", "color": "gray"}, {"name": "Done", "color": "green"}]})
        )
        story = backlog / "LK-0001-story.md"
        story.write_text(
            "# LK-0001\n\n| **Status** | Not Started |\n\n---\n## History\n- created\n\n---\n"
        )
        script = IDLE_SERVER.parent.parent.parent / "update-status" / "scripts" / "update-status.sh"
        result = subprocess.run([str(script), str(story), "Done"], capture_output=True, text=True)
        assert result.returncode == 0
        assert not (backlog / f"{story.name}.lock").exists()
