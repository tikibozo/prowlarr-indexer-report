#!/usr/bin/env python3
"""Preview the report UI without a real Prowlarr.

Serves the static front-end (`app/static/`) plus a representative `/api/data`
built from fictional indexers — no Prowlarr, no API key, no network. Useful for
UI work and for regenerating the README screenshot (`docs/report.png`).

    python dev/mock_server.py            # then open http://localhost:8787
    python dev/mock_server.py --port 9000

The indexer names here are invented for the demo; any resemblance to a real
tracker is coincidental. Every date is expressed as an age in days and resolved
at request time, so the demo reads as freshly generated whenever it is run — and
so the time-window picker has coherent data to slice. The verdict rules below
mirror ``app.prowlarr``; this file stays stdlib-only on purpose.
"""
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

STATIC_DIR = Path(__file__).resolve().parent.parent / "app" / "static"
APPS = ["Sonarr", "Radarr", "Lidarr", "Readarr"]
DEFAULT_WINDOW = 90
WINDOWS: list[int | None] = [7, 30, 90, 180, 365, None]   # None = all retained history
SPAN_DAYS = 330                                           # history the fake Prowlarr retains
CONTENT_TYPES = {".html": "text/html", ".js": "text/javascript", ".css": "text/css"}


def _window_meta(days: int | None) -> dict:
    if days is None:
        return {"key": "all", "days": None, "short": "All time",
                "label": "all retained history"}
    if days % 365 == 0:
        years = days // 365
        label = "the last year" if years == 1 else f"the last {years} years"
    elif days % 30 == 0 and days >= 60:
        months = days // 30
        label = f"the last {months} months"
    else:
        label = f"the last {days} days"
    return {"key": str(days), "days": days, "short": f"{days}d", "label": label}


METAS = [_window_meta(d) for d in WINDOWS]


def _row(name, protocol, enabled, grabs_all, queries, fail_rate, resp, last_grab_days,
         per_app, auto_search=True, app_profile="Standard", priority=25):
    """One fictional indexer. ``last_grab_days`` is an age; None = never grabbed."""
    return {
        "name": name, "protocol": protocol, "enabled": enabled, "priority": priority,
        "grabsAll": grabs_all, "queries": queries, "failRate": fail_rate, "respTime": resp,
        "lastGrabDays": last_grab_days, "perApp": per_app,
        "autoSearch": auto_search, "appProfile": app_profile,
    }


# Fictional indexers, chosen to exercise every flag and a realistic spread.
ROWS = [
    # Strong performers
    _row("Nimbus News", "usenet", True, 7240, 21000, 0.4, 520, 1,
         {"Sonarr": 4200, "Radarr": 2600, "Lidarr": 300, "Readarr": 140}, priority=10),
    _row("Orchard NZB", "usenet", True, 4980, 14200, 0.6, 610, 2,
         {"Sonarr": 2900, "Radarr": 1900, "Readarr": 180}, priority=15),
    _row("RedHarbor", "torrent", True, 3640, 11200, 1.1, 720, 1,
         {"Sonarr": 2100, "Radarr": 1500, "Lidarr": 40}),
    _row("Helix Usenet", "usenet", True, 3110, 9800, 0.7, 690, 3,
         {"Sonarr": 1800, "Radarr": 1200, "Lidarr": 110}),
    # Mid performers
    _row("IronBay", "torrent", True, 2290, 8800, 1.6, 810, 4,
         {"Sonarr": 1300, "Radarr": 990}),
    _row("Thornwood", "torrent", True, 1480, 6900, 2.0, 760, 6,
         {"Sonarr": 900, "Radarr": 560, "Lidarr": 20}),
    _row("Vellum Bin", "usenet", True, 880, 5400, 0.9, 700, 8,
         {"Sonarr": 520, "Radarr": 360}),
    _row("Saffron", "torrent", True, 610, 2300, 0.8, 540, 1, {"Sonarr": 610}),
    # Watch — high query cost, near-zero grab rate
    _row("Gallium", "torrent", True, 31, 9100, 0.7, 930, 16, {"Radarr": 31}),
    _row("Cobalt NZB", "usenet", True, 18, 6400, 0.9, 880, 18, {"Radarr": 18}),
    # Remove — nothing inside the window, or nothing ever
    _row("Cinder Tracker", "torrent", True, 540, 3100, 1.4, 770, 131, {"Sonarr": 540}),
    _row("Driftwood", "torrent", True, 0, 4200, 1.1, 950, None, {}),
    _row("Mossgarden", "usenet", True, 0, 2600, 0.8, 700, None, {}),
    # Manual — interactive-only profile, not expected to auto-grab
    _row("Tin Roof", "torrent", True, 1860, 4200, 0.5, 540, 158, {"Radarr": 1860},
         auto_search=False, app_profile="Interactive"),
    _row("Lantern News", "usenet", True, 420, 1400, 0.6, 620, 140, {"Sonarr": 420},
         auto_search=False, app_profile="Interactive"),
    # Disabled
    _row("Quartz", "torrent", False, 230, 900, 1.9, 1020, 291, {"Sonarr": 230}, priority=50),
    _row("Stale Bin", "usenet", False, 0, 140, 3.2, 1500, None, {}, priority=50),
]


def _window_grabs(row: dict, days: int | None) -> int:
    """Grabs inside one window: a flat share of the retained span, zero once the
    indexer's last grab predates the window."""
    if days is None:
        return row["grabsAll"]
    age = row["lastGrabDays"]
    if age is None or age > days or not row["grabsAll"]:
        return 0
    return max(1, round(row["grabsAll"] * min(days, SPAN_DAYS) / SPAN_DAYS))


def _verdict(row: dict, grabs_win: int, short: str, last: str) -> tuple[str, str]:
    """Same precedence as app.prowlarr: disabled > manual > remove > watch."""
    grabs_all, queries = row["grabsAll"], row["queries"]
    rate = (grabs_all / queries) if queries else 0.0
    if not row["enabled"]:
        return ("disabled", "Already disabled, never grabbed") if grabs_all == 0 else ("", "")
    if not row["autoSearch"]:
        return "manual", (
            f"Manual/interactive-only profile ({row['appProfile']}) — automatic search off"
        )
    if grabs_all == 0:
        return "remove", f"Never grabbed anything ({queries} queries)"
    if grabs_win == 0:
        return "remove", f"No grabs in {short} (last: {last or 'unknown'})"
    if queries >= 5000 and rate < 0.005:
        return "watch", f"High cost: {queries} queries, {rate * 100:.2f}% grab rate"
    return "", ""


def _indexers(today: datetime) -> list[dict]:
    out = []
    for row in ROWS:
        age = row["lastGrabDays"]
        last = "" if age is None else (today - timedelta(days=age)).strftime("%Y-%m-%d")
        queries = row["queries"]
        by_window = {}
        for meta in METAS:
            grabs = _window_grabs(row, meta["days"])
            flag, reason = _verdict(row, grabs, meta["short"], last)
            by_window[meta["key"]] = {"grabs": grabs, "flag": flag, "reason": reason}
        sel = by_window[str(DEFAULT_WINDOW)]
        out.append({
            "id": abs(hash(row["name"])) % 100000, "name": row["name"],
            "protocol": row["protocol"], "enabled": row["enabled"],
            "priority": row["priority"], "grabsAll": row["grabsAll"],
            "grabsWin": sel["grabs"], "grabs30": by_window["30"]["grabs"],
            "queries": queries,
            "grabRate": round(row["grabsAll"] / queries * 100, 3) if queries else 0.0,
            "failRate": row["failRate"], "respTime": row["respTime"],
            "grabRespTime": row["respTime"], "lastGrab": last, "perApp": row["perApp"],
            "autoSearch": row["autoSearch"], "appProfile": row["appProfile"],
            "flag": sel["flag"], "reason": sel["reason"], "byWindow": by_window,
        })
    out.sort(key=lambda r: r["grabsAll"], reverse=True)
    return out


def _timeline(today: datetime) -> list[list]:
    """Eleven months of monthly grab volume ending in the current month."""
    shape = [1180, 1620, 2040, 2480, 2960, 3240, 2880, 2510, 2190, 1980, 1460]
    months, cursor = [], today.replace(day=1)
    for _ in shape:
        months.append(cursor.strftime("%Y-%m"))
        cursor = (cursor - timedelta(days=1)).replace(day=1)
    return [[m, n] for m, n in zip(reversed(months), shape, strict=True)]


def build_payload():
    today = datetime.now(UTC)
    now = today.isoformat()
    rows = _indexers(today)
    summary_by_window = {
        m["key"]: {
            "indexers": len(rows),
            "enabled": sum(1 for r in rows if r["enabled"]),
            "totalGrabs": sum(r["grabsAll"] for r in rows),
            "windowGrabs": sum(r["byWindow"][m["key"]]["grabs"] for r in rows),
            "removeCandidates": sum(1 for r in rows if r["byWindow"][m["key"]]["flag"] == "remove"),
            "watchCandidates": sum(1 for r in rows if r["byWindow"][m["key"]]["flag"] == "watch"),
            "manual": sum(1 for r in rows if r["byWindow"][m["key"]]["flag"] == "manual"),
        }
        for m in METAS
    }
    return {
        "generatedAt": now, "fetchedAt": now,
        "windowDays": DEFAULT_WINDOW, "defaultWindow": str(DEFAULT_WINDOW),
        "windows": METAS, "refreshIntervalMinutes": 15, "lastError": None,
        "prowlarrUrl": "http://localhost:9696",
        "history": {
            "start": (today - timedelta(days=SPAN_DAYS)).strftime("%Y-%m-%d"),
            "end": today.strftime("%Y-%m-%d"),
            "spanDays": SPAN_DAYS, "truncated": False,
        },
        "apps": APPS, "timeline": _timeline(today), "indexers": rows,
        "summary": summary_by_window[str(DEFAULT_WINDOW)],
        "summaryByWindow": summary_by_window,
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
