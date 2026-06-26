#!/usr/bin/env python3
"""Preview the report UI without a real Prowlarr.

Serves the static front-end (`app/static/`) plus a representative `/api/data`
built from fictional indexers — no Prowlarr, no API key, no network. Useful for
UI work and for regenerating the README screenshot (`docs/report.png`).

    python dev/mock_server.py            # then open http://localhost:8787
    python dev/mock_server.py --port 9000

The indexer names here are invented for the demo; any resemblance to a real
tracker is coincidental. `generatedAt` is stamped at request time so the live
status line reads as fresh.
"""
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

STATIC_DIR = Path(__file__).resolve().parent.parent / "app" / "static"
APPS = ["Sonarr", "Radarr", "Lidarr", "Readarr"]
WINDOW_DAYS = 90
CONTENT_TYPES = {".html": "text/html", ".js": "text/javascript", ".css": "text/css"}


def _row(name, protocol, enabled, grabs_all, grabs_win, grabs_30, queries,
         fail_rate, resp, last_grab, per_app, flag="", reason="",
         auto_search=True, app_profile="Standard", priority=25):
    grab_rate = round((grabs_all / queries * 100), 3) if queries else 0.0
    return {
        "id": abs(hash(name)) % 100000, "name": name, "protocol": protocol,
        "enabled": enabled, "priority": priority,
        "grabsAll": grabs_all, "grabsWin": grabs_win, "grabs30": grabs_30,
        "queries": queries, "grabRate": grab_rate, "failRate": fail_rate,
        "respTime": resp, "grabRespTime": resp, "lastGrab": last_grab,
        "perApp": per_app, "autoSearch": auto_search, "appProfile": app_profile,
        "flag": flag, "reason": reason,
    }


# Fictional indexers, chosen to exercise every flag and a realistic spread.
ROWS = [
    # Strong performers
    _row("Nimbus News", "usenet", True, 7240, 2100, 320, 21000, 0.4, 520, "2026-06-25",
         {"Sonarr": 4200, "Radarr": 2600, "Lidarr": 300, "Readarr": 140}),
    _row("Orchard NZB", "usenet", True, 4980, 1500, 210, 14200, 0.6, 610, "2026-06-24",
         {"Sonarr": 2900, "Radarr": 1900, "Readarr": 180}),
    _row("RedHarbor", "torrent", True, 3640, 1100, 240, 11200, 1.1, 720, "2026-06-25",
         {"Sonarr": 2100, "Radarr": 1500, "Lidarr": 40}),
    _row("Helix Usenet", "usenet", True, 3110, 900, 130, 9800, 0.7, 690, "2026-06-23",
         {"Sonarr": 1800, "Radarr": 1200, "Lidarr": 110}),
    # Mid performers
    _row("IronBay", "torrent", True, 2290, 640, 90, 8800, 1.6, 810, "2026-06-22",
         {"Sonarr": 1300, "Radarr": 990}),
    _row("Thornwood", "torrent", True, 1480, 280, 30, 6900, 2.0, 760, "2026-06-20",
         {"Sonarr": 900, "Radarr": 560, "Lidarr": 20}),
    _row("Vellum Bin", "usenet", True, 880, 150, 12, 5400, 0.9, 700, "2026-06-19",
         {"Sonarr": 520, "Radarr": 360}),
    _row("Saffron", "torrent", True, 610, 130, 24, 2300, 0.8, 540, "2026-06-25",
         {"Sonarr": 610}),
    # Watch — high query cost, near-zero grab rate
    _row("Gallium", "torrent", True, 31, 2, 0, 9100, 0.7, 930, "2026-06-10",
         {"Radarr": 31}, flag="watch", reason="High cost: 9100 queries, 0.34% grab rate"),
    _row("Cobalt NZB", "usenet", True, 18, 4, 0, 6400, 0.9, 880, "2026-06-08",
         {"Radarr": 18}, flag="watch", reason="High cost: 6400 queries, 0.28% grab rate"),
    # Remove — never grabbed, or nothing inside the window
    _row("Cinder Tracker", "torrent", True, 540, 0, 0, 3100, 1.4, 770, "2026-02-14",
         {"Sonarr": 540}, flag="remove", reason="No grabs in 90d (last: 2026-02-14)"),
    _row("Driftwood", "torrent", True, 0, 0, 0, 4200, 1.1, 950, "",
         {}, flag="remove", reason="Never grabbed anything (4200 queries)"),
    _row("Mossgarden", "usenet", True, 0, 0, 0, 2600, 0.8, 700, "",
         {}, flag="remove", reason="Never grabbed anything (2600 queries)"),
    # Manual — interactive-only profile, not expected to auto-grab
    _row("Tin Roof", "torrent", True, 1860, 0, 0, 1200, 0.5, 540, "2026-03-15",
         {"Radarr": 1860}, flag="manual", auto_search=False, app_profile="Interactive",
         reason="Manual/interactive-only profile (Interactive) — automatic search off"),
    _row("Lantern News", "usenet", True, 420, 0, 0, 600, 0.6, 620, "2026-04-02",
         {"Sonarr": 420}, flag="manual", auto_search=False, app_profile="Interactive",
         reason="Manual/interactive-only profile (Interactive) — automatic search off"),
    # Disabled
    _row("Quartz", "torrent", False, 230, 0, 0, 900, 1.9, 1020, "2025-11-02",
         {"Sonarr": 230}),
    _row("Stale Bin", "usenet", False, 0, 0, 0, 140, 3.2, 1500, "",
         {}, flag="disabled", reason="Already disabled, never grabbed"),
]

TIMELINE = [
    ["2025-08", 1180], ["2025-09", 1620], ["2025-10", 2040], ["2025-11", 2480],
    ["2025-12", 2960], ["2026-01", 3240], ["2026-02", 2880], ["2026-03", 2510],
    ["2026-04", 2190], ["2026-05", 1980], ["2026-06", 1460],
]


def build_payload():
    now = datetime.now(UTC).isoformat()
    return {
        "generatedAt": now, "fetchedAt": now,
        "windowDays": WINDOW_DAYS, "refreshIntervalMinutes": 15, "lastError": None,
        "prowlarrUrl": "http://localhost:9696",
        "history": {"start": "2025-08-01", "spanDays": 330, "truncated": False},
        "apps": APPS, "timeline": TIMELINE, "indexers": ROWS,
        "summary": {
            "indexers": len(ROWS),
            "enabled": sum(1 for r in ROWS if r["enabled"]),
            "totalGrabs": sum(r["grabsAll"] for r in ROWS),
            "removeCandidates": sum(1 for r in ROWS if r["flag"] == "remove"),
            "watchCandidates": sum(1 for r in ROWS if r["flag"] == "watch"),
            "manual": sum(1 for r in ROWS if r["flag"] == "manual"),
        },
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # quiet
        pass

    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path.split("?")[0] == "/api/refresh":
            self._send(200, b"{}", "application/json")
        else:
            self._send(404, b"not found", "text/plain")

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/api/data":
            self._send(200, json.dumps(build_payload()).encode(), "application/json")
            return
        rel = "index.html" if path == "/" else path.removeprefix("/static/").lstrip("/")
        target = (STATIC_DIR / rel).resolve()
        if STATIC_DIR not in target.parents or not target.is_file():
            self._send(404, b"not found", "text/plain")
            return
        self._send(200, target.read_bytes(),
                   CONTENT_TYPES.get(target.suffix, "application/octet-stream"))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Mock report UI on http://{args.host}:{args.port}  (Ctrl-C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
