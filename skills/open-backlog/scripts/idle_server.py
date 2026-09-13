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
import os
import socketserver
import sys
import threading
import time

PORT = int(sys.argv[1])
DIRECTORY = sys.argv[2]
IDLE_TIMEOUT = 30 * 60  # 30 minutes — matches the time an unattended tab is
                        # assumed abandoned, not the time a single click takes

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
