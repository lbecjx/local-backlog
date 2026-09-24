#!/usr/bin/env python3
# local-backlog — a local issue/story tracker for Claude Code, no cloud account needed
# Copyright (C) 2026  lbecjx
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version. See LICENSE for the full text.

# A drop-in replacement for `python3 -m http.server <port> --directory <dir>`
# that shuts itself down after IDLE_TIMEOUT seconds with no requests — so a
# forgotten viewer doesn't sit consuming RAM forever. open-backlog.sh already
# checks whether the previous server's PID is still alive before reusing it,
# so a self-terminated server is picked up as "needs a fresh one" automatically,
# with no extra logic needed on that side.

import http.server
import json
import os
import re
import socketserver
import subprocess
import sys
import threading
import time
import urllib.parse

PORT = int(sys.argv[1])
DIRECTORY = sys.argv[2]
IDLE_TIMEOUT = 30 * 60  # 30 minutes — matches the time an unattended tab is
                        # assumed abandoned, not the time a single click takes

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
UPDATE_STATUS_SCRIPT = os.path.join(SCRIPT_DIR, "..", "..", "update-status", "scripts", "update-status.sh")
SET_BOARD_SCRIPT = os.path.join(SCRIPT_DIR, "..", "..", "update-status", "scripts", "set-board.sh")

# Same shape as the grep pattern in update-status/scripts/set-board.sh —
# no shared source of truth across Python and bash, so keep both in sync
# by hand if the <PREFIX>-XXXX format ever changes.
CODE_PATTERN = re.compile(r"^[A-Z]{2,6}-[0-9]{4}$")

# Zone and resolution values, duplicated as literals in
# update-status/scripts/set-board.sh (which validates them again on its
# own side, independent of this server) — same "keep in sync by hand" note
# as CODE_PATTERN above.
VALID_ZONES = ("backlog", "planner", "archive")
VALID_RESOLUTIONS = ("Done", "Won't Do")

last_activity = time.time()
activity_lock = threading.Lock()


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def log_message(self, format, *args):
        # Every completed request calls this — reuse it as the activity hook
        # instead of overriding each HTTP verb, and stay quiet (no stdout
        # noise from a background process nobody is watching).
        global last_activity
        with activity_lock:
            last_activity = time.time()

    def _send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _sanitize_error(self, text):
        # update-status.sh/set-board.sh embed the full absolute path they
        # were called with in their own error text (useful when read from a
        # terminal via the slash-command path). This server used to be
        # read-only, so that text never reached anyone but the person who
        # typed the command; now it's relayed straight into an HTTP response
        # any tab on the machine could read. Strip the one prefix we know is
        # always there (this server's own served directory) rather than the
        # full absolute path, so the relative remainder — still useful for
        # diagnosing which file/lock the error is about — survives.
        return text.replace(DIRECTORY.rstrip("/") + "/", "").replace(DIRECTORY, "")

    def _resolve_story_file(self, code):
        # `code` is already checked against CODE_PATTERN by the caller before
        # this runs. Matching by exact filename prefix inside a fixed,
        # known directory (never string-concatenating `code` into a path)
        # means there is no way for this to resolve outside backlog_dir.
        # os.listdir's order is filesystem-dependent, not sorted — sorting
        # here makes the result deterministic, and collecting every match
        # (instead of returning on the first hit) lets the caller detect and
        # reject the ambiguous case of two files sharing a code prefix
        # (e.g. an orphaned file left behind by a partial rename) instead of
        # silently picking one.
        backlog_dir = os.path.join(DIRECTORY, "backlog")
        return sorted(
            name for name in os.listdir(backlog_dir) if name.startswith(code + "-") and name.endswith(".md")
        )

    def _read_status(self, story_file):
        # Same row this update-status.sh reads/writes, parsed directly here
        # (not by shelling out) so a rollback has the exact pre-change value
        # to restore, without depending on parsing another script's stdout.
        try:
            with open(story_file, errors="replace") as f:
                for line in f:
                    m = re.match(r"\|\s*\*\*Status\*\*\s*\|\s*(.*?)\s*\|\s*$", line)
                    if m:
                        return m.group(1)
        except OSError:
            pass
        return None

    def _known_statuses(self, story_file):
        # None means "no closed list for this project" (any status accepted,
        # same backward-compat rule update-status.sh itself follows) — not
        # the same as an empty list, which would mean "nothing is valid."
        statuses_file = os.path.join(os.path.dirname(story_file), ".backlog-statuses.json")
        if not os.path.isfile(statuses_file):
            return None
        try:
            with open(statuses_file) as f:
                data = json.load(f)
            return {entry["name"] for entry in data.get("statuses", [])}
        except (OSError, json.JSONDecodeError, KeyError, TypeError):
            return None

    def _from_this_server(self):
        # This server was read-only until this task group — no other page
        # open in the browser could ever make it act on their behalf. A
        # write endpoint changes that, and there's no login/token of any
        # kind here (it's a personal local tool), so this is the one thing
        # standing between "only this app can write here" and "any tab in
        # your browser can write here silently." Real browser requests from
        # this app carry Origin (or, lacking that, Referer) pointing at
        # this exact server; anything else is untrusted.
        # A raw string-prefix check here would be exploitable: e.g.
        # "http://localhost:80001".startswith("http://localhost:8000") is
        # True, so a page on a numerically-extending port could pass. Parse
        # and compare scheme/host/port exactly instead.
        source = self.headers.get("Origin") or self.headers.get("Referer") or ""
        try:
            parsed = urllib.parse.urlsplit(source)
            return parsed.scheme == "http" and parsed.hostname in ("localhost", "127.0.0.1") and parsed.port == PORT
        except ValueError:
            # Malformed host/port (e.g. a port number out of the valid TCP
            # range) — urlsplit or the .port access itself can raise here.
            # Treat as untrusted rather than letting the exception crash
            # this request's handler thread.
            return False

    def _handle_archive(self, story_file, board_args):
        # AC #9: archiving a story that isn't already Done must set its
        # Status to Done. update-status.sh already no-ops cleanly ("Status
        # is already 'Done' — nothing to do.") when it's called with the
        # status the story already has, so calling it unconditionally here
        # — rather than checking "not already Done" ourselves — gets that
        # for free. But the two writes (Status, then board membership)
        # aren't one transaction: if the Status flip succeeds and the board
        # write then fails (e.g. a corrupted .backlog-board.json), the
        # story would be permanently stuck showing Done without ever
        # actually reaching the Archive. old_status is captured first so
        # that exact failure can be rolled back rather than left half-done.
        old_status = self._read_status(story_file)
        # If the rollback below ever has to run, it re-sets Status to
        # old_status — which only works if old_status is itself a
        # recognized value (update-status.sh validates whatever it's asked
        # to SET, not what a file already has). A story whose Status
        # predates .backlog-statuses.json, or was left invalid by some
        # other means, would make that rollback call fail the same
        # closed-list check meant to prevent bad data — leaving the story
        # stuck at Done with nothing ever recorded in Archive and no way
        # back except a hand edit. Refusing up front, before touching
        # anything, is what keeps the closed list an actual guarantee
        # instead of one with a rollback-shaped hole in it.
        known_statuses = self._known_statuses(story_file)
        if old_status is not None and known_statuses is not None and old_status not in known_statuses:
            self._send_json(
                409,
                {
                    "error": f"story's current Status '{old_status}' isn't a recognized "
                    f"status — fix it before archiving"
                },
            )
            return

        status_result = subprocess.run([UPDATE_STATUS_SCRIPT, story_file, "Done"], capture_output=True, text=True)
        if status_result.returncode != 0:
            # Exit code 2 means update-status.sh rejected "Done" itself as
            # not one of this project's known statuses (a customized
            # .backlog-statuses.json that dropped it) — a bad request, not
            # a server-side failure; everything else (1) stays a 500.
            error_status = 400 if status_result.returncode == 2 else 500
            self._send_json(
                error_status,
                {"error": self._sanitize_error(status_result.stderr.strip() or status_result.stdout.strip())},
            )
            return

        # If the board write below fails and a rollback is needed, the
        # value to restore must be whatever update-status.sh itself just
        # read as the "from" state for THIS transition — not old_status
        # (captured earlier, before this call, purely for the pre-flight
        # 409 check above). A concurrent /api/status write landing between
        # that early read and this call would make old_status stale;
        # update-status.sh's own read happens atomically as part of its own
        # lock-protected write and already reflects whatever was actually
        # current at THAT moment. Parsed from its stdout ("Status: X → Y")
        # rather than re-derived here, so this can never drift from what
        # the script actually did.
        transition_line = status_result.stdout.strip().splitlines()[0] if status_result.stdout.strip() else ""
        transition_match = re.match(r"^Status: (.+) → .+$", transition_line)
        rollback_target = transition_match.group(1) if transition_match else None

        board_result = subprocess.run(board_args, capture_output=True, text=True)
        if board_result.returncode == 0:
            self._send_json(200, {"result": board_result.stdout.strip()})
            return

        board_error = self._sanitize_error(board_result.stderr.strip() or board_result.stdout.strip())
        if not rollback_target or rollback_target == "Done":
            self._send_json(500, {"error": board_error})
            return

        # A *second* concurrent write could still land between our own Done
        # write above and this rollback — the same class of window, one
        # step later. Re-reading Status right before rolling back and only
        # doing so if it's still exactly what OUR own write just set
        # ("Done") closes that one too: if someone else already moved it on
        # again, we leave their value alone instead of clobbering it.
        current_status = self._read_status(story_file)
        if current_status != "Done":
            self._send_json(
                500,
                {
                    "error": f"Archiving failed (board write) — Status left as-is "
                    f"because it changed concurrently: {board_error}"
                },
            )
            return

        # Known, accepted limitation: a successful rollback still leaves
        # two real History lines (old→Done, then Done→old) for an action
        # the human experiences as a single failed attempt —
        # update-status.sh's History format has no way to mark an entry as
        # "part of a rolled-back sequence." Correctness (Status ends up
        # back where it was) matters more here than the cosmetic
        # double-entry, and the story's own error response below says
        # plainly that it was rolled back.
        rollback = subprocess.run([UPDATE_STATUS_SCRIPT, story_file, rollback_target], capture_output=True, text=True)
        if rollback.returncode == 0:
            self._send_json(500, {"error": f"Archiving failed, Status rolled back: {board_error}"})
        else:
            self._send_json(
                500,
                {
                    "error": f"Archiving failed AND rollback failed — Status may be "
                    f"incorrectly Done: {board_error}"
                },
            )

    def do_POST(self):
        if not self._from_this_server():
            self._send_json(403, {"error": "request did not originate from this server"})
            return

        # Checked before anything else about the body: a request for a
        # route that doesn't exist should say so, regardless of whether its
        # JSON or its 'code' field also happens to be malformed — checking
        # this after those (as an earlier version of this method did) meant
        # a bad code on an unknown path was misreported as a code problem.
        if self.path not in ("/api/status", "/api/board"):
            self._send_json(404, {"error": f"no such endpoint: {self.path}"})
            return

        length = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(length))
        except json.JSONDecodeError:
            self._send_json(400, {"error": "malformed JSON body"})
            return

        code = payload.get("code", "")
        if not isinstance(code, str) or not CODE_PATTERN.match(code):
            self._send_json(400, {"error": "missing or invalid 'code'"})
            return

        matches = self._resolve_story_file(code)
        if len(matches) == 0:
            self._send_json(404, {"error": f"no story file found for code {code}"})
            return
        if len(matches) > 1:
            self._send_json(500, {"error": f"{len(matches)} story files share code {code}: {', '.join(matches)}"})
            return
        story_file = os.path.join(DIRECTORY, "backlog", matches[0])

        if self.path == "/api/status":
            status = payload.get("status", "")
            if not isinstance(status, str) or not status:
                self._send_json(400, {"error": "missing 'status'"})
                return
            args = [UPDATE_STATUS_SCRIPT, story_file, status]
        else:  # self.path == "/api/board" — the only other value possible after the check above
            zone = payload.get("zone", "")
            if zone not in VALID_ZONES:
                self._send_json(400, {"error": f"'zone' must be one of: {', '.join(VALID_ZONES)}"})
                return
            resolution = payload.get("resolution")
            # Checked unconditionally, not just when zone == "archive": a
            # non-string resolution sent alongside zone in ("backlog",
            # "planner") would otherwise reach subprocess.run's argv
            # untyped-checked below and crash the handler thread instead of
            # returning a clean 400 (found by two independent review passes).
            if resolution is not None and not isinstance(resolution, str):
                self._send_json(400, {"error": "'resolution' must be a string"})
                return
            if zone == "archive" and resolution not in VALID_RESOLUTIONS:
                self._send_json(
                    400, {"error": f"archiving requires 'resolution' to be one of: {', '.join(VALID_RESOLUTIONS)}"}
                )
                return
            reason = payload.get("reason")
            if reason is not None and not isinstance(reason, str):
                self._send_json(400, {"error": "'reason' must be a string"})
                return
            board_args = [SET_BOARD_SCRIPT, story_file, zone]
            if resolution is not None:
                board_args += ["--resolution", resolution]
            if reason:
                board_args += ["--reason", reason]

            if zone == "archive":
                self._handle_archive(story_file, board_args)
                return

            args = board_args

        result = subprocess.run(args, capture_output=True, text=True)
        if result.returncode == 0:
            self._send_json(200, {"result": result.stdout.strip()})
        else:
            # Same distinction as _handle_archive's own status_result check:
            # exit code 2 from update-status.sh means the requested status
            # itself was invalid (a bad request), not a server-side failure.
            error_status = 400 if result.returncode == 2 else 500
            self._send_json(error_status, {"error": self._sanitize_error(result.stderr.strip() or result.stdout.strip())})


def watchdog():
    while True:
        time.sleep(60)
        with activity_lock:
            idle_for = time.time() - last_activity
        if idle_for > IDLE_TIMEOUT:
            os._exit(0)  # no state to flush — just static files, exit immediately


threading.Thread(target=watchdog, daemon=True).start()

with socketserver.ThreadingTCPServer(("", PORT), Handler) as httpd:
    httpd.serve_forever()
