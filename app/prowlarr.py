"""Prowlarr API client and report computation.

The data layer is split in two so the analysis is trivially testable:

  * ``ProwlarrClient`` does the (async) HTTP I/O against the Prowlarr v1 API.
  * ``compute_report`` is a pure function over already-fetched payloads.

Data sources (all read-only):
  * GET /api/v1/indexer        — name, protocol, enable, priority
  * GET /api/v1/indexerstats   — per-indexer aggregates; accepts ?startDate=
                                 &endDate= (ISO-8601 Z) for windowed totals.
  * GET /api/v1/history?eventType=1 — per-grab events carrying data.source
                                 (the consuming app) + date. The ONLY source
                                 of the per-app breakdown and grabs timeline.
"""
from __future__ import annotations

import datetime as _dt
from typing import Any

import httpx

# Apps we normalize the free-form history `data.source` field onto.
_KNOWN_APPS = ("sonarr", "radarr", "lidarr", "readarr", "whisparr", "prowlarr")


def iso(dt: _dt.datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def now_utc() -> _dt.datetime:
    return _dt.datetime.now(_dt.UTC)


class ProwlarrClient:
    def __init__(self, base_url: str, api_key: str, *, timeout: float = 60.0) -> None:
        self._base = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self._base,
            headers={"X-Api-Key": api_key},
            timeout=timeout,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        resp = await self._client.get(path, params=params)
        resp.raise_for_status()
        return resp.json()

    async def indexers(self) -> list[dict]:
        return await self._get("/api/v1/indexer")

    async def stats(
        self, start: _dt.datetime | None = None, end: _dt.datetime | None = None
    ) -> list[dict]:
        params = None
        if start and end:
            params = {"startDate": iso(start), "endDate": iso(end)}
        data = await self._get("/api/v1/indexerstats", params=params)
        return data.get("indexers", [])

    async def history_grabs(
        self, *, page_size: int = 1000, max_pages: int = 250
    ) -> tuple[list[dict], bool]:
        """Page ALL grab events (eventType=1) Prowlarr retains.

        Prowlarr aggregates indexerstats from the same History table it serves
        here, and prunes both at ``historycleanupdays`` (default 30) — so "all
        retained history" is the most that exists, and this pages every page of
        it. Returns ``(records, truncated)``; ``truncated`` is True only if we
        hit ``max_pages`` before exhausting ``totalRecords`` (a safety backstop,
        not normally reached — surfaced to the UI so truncation is never silent).
        """
        out: list[dict] = []
        truncated = False
        for page in range(1, max_pages + 1):
            data = await self._get(
                "/api/v1/history",
                params={
                    "eventType": 1,
                    "page": page,
                    "pageSize": page_size,
                    "sortKey": "date",
                    "sortDirection": "descending",
                },
            )
            records = data.get("records", [])
            out.extend(records)
            total = data.get("totalRecords", 0)
            if len(out) >= total or not records:
                break
            if page == max_pages:
                truncated = True
        return out, truncated


def normalize_source(src: str | None) -> str:
    if not src:
        return "Other"
    low = src.strip().lower()
    for app in _KNOWN_APPS:
        if app in low:
            return app.capitalize()
    return src.strip()


def _stats_by_id(rows: list[dict]) -> dict[int, dict]:
    return {r["indexerId"]: r for r in rows}


def compute_report(
    *,
    indexers: list[dict],
    all_stats: list[dict],
    window_stats: list[dict],
    d30_stats: list[dict],
    history: list[dict],
    window_days: int,
    generated_at: _dt.datetime,
    history_truncated: bool = False,
) -> dict:
    """Pure transform of raw Prowlarr payloads into the report data model."""
    all_by = _stats_by_id(all_stats)
    win_by = _stats_by_id(window_stats)
    d30_by = _stats_by_id(d30_stats)

    per_app: dict[int, dict[str, int]] = {}
    timeline: dict[str, int] = {}
    last_grab: dict[int, str] = {}
    apps_seen: set[str] = set()
    earliest_grab: str | None = None  # span of grab history actually retained
    latest_grab: str | None = None
    for rec in history:
        iid = rec.get("indexerId")
        app = normalize_source((rec.get("data") or {}).get("source"))
        apps_seen.add(app)
        per_app.setdefault(iid, {}).setdefault(app, 0)
        per_app[iid][app] += 1
        date = rec.get("date", "")
        if date:
            month = date[:7]
            timeline[month] = timeline.get(month, 0) + 1
            if iid not in last_grab or date > last_grab[iid]:
                last_grab[iid] = date
            if earliest_grab is None or date < earliest_grab:
                earliest_grab = date
            if latest_grab is None or date > latest_grab:
                latest_grab = date

    rows: list[dict] = []
    for ix in indexers:
        iid = ix["id"]
        a, w, d = all_by.get(iid, {}), win_by.get(iid, {}), d30_by.get(iid, {})
        queries = a.get("numberOfQueries", 0) or 0
        grabs_all = a.get("numberOfGrabs", 0) or 0
        grabs_win = w.get("numberOfGrabs", 0) or 0
        grabs_30 = d.get("numberOfGrabs", 0) or 0
        failed_q = a.get("numberOfFailedQueries", 0) or 0
        grab_rate = (grabs_all / queries) if queries else 0.0
        fail_rate = (failed_q / queries) if queries else 0.0

        flag, reason = "", ""
        if ix.get("enable", True):
            if grabs_all == 0:
                flag, reason = "remove", f"Never grabbed anything ({queries} queries)"
            elif grabs_win == 0:
                last = (last_grab.get(iid, "") or "")[:10] or "unknown"
                flag, reason = "remove", f"No grabs in {window_days}d (last: {last})"
            elif queries >= 5000 and grab_rate < 0.005:
                flag, reason = "watch", (
                    f"High cost: {queries} queries, {grab_rate * 100:.2f}% grab rate"
                )
        elif grabs_all == 0:
            flag, reason = "disabled", "Already disabled, never grabbed"

        rows.append(
            {
                "id": iid,
                "name": ix.get("name", "?"),
                "protocol": ix.get("protocol", "?"),
                "enabled": bool(ix.get("enable", True)),
                "priority": ix.get("priority", 25),
                "grabsAll": grabs_all,
                "grabsWin": grabs_win,
                "grabs30": grabs_30,
                "queries": queries,
                "grabRate": round(grab_rate * 100, 3),
                "failRate": round(fail_rate * 100, 3),
                "respTime": a.get("averageResponseTime", 0) or 0,
                "grabRespTime": a.get("averageGrabResponseTime", 0) or 0,
                "lastGrab": (last_grab.get(iid, "") or "")[:10],
                "perApp": per_app.get(iid, {}),
                "flag": flag,
                "reason": reason,
            }
        )

    rows.sort(key=lambda r: r["grabsAll"], reverse=True)
    summary = {
        "indexers": len(rows),
        "enabled": sum(1 for r in rows if r["enabled"]),
        "totalGrabs": sum(r["grabsAll"] for r in rows),
        "removeCandidates": sum(1 for r in rows if r["flag"] == "remove"),
        "watchCandidates": sum(1 for r in rows if r["flag"] == "watch"),
    }
    span_days = None
    if earliest_grab and latest_grab:
        span_days = (_dt.datetime.fromisoformat(latest_grab.replace("Z", "+00:00"))
                     - _dt.datetime.fromisoformat(earliest_grab.replace("Z", "+00:00"))).days
    return {
        "generatedAt": iso(generated_at),
        "windowDays": window_days,
        "summary": summary,
        # Span of grab history Prowlarr actually retains (bounded by its
        # historycleanupdays). historyTruncated flags the rare case where paging
        # hit its page cap, so the UI can warn instead of silently undercounting.
        "history": {
            "start": (earliest_grab or "")[:10],
            "end": (latest_grab or "")[:10],
            "spanDays": span_days,
            "truncated": history_truncated,
        },
        "indexers": rows,
        "apps": sorted(apps_seen),
        "timeline": sorted(timeline.items()),
    }


async def build_report(client: ProwlarrClient, window_days: int) -> dict:
    """Fetch everything from Prowlarr and compute the report data model."""
    now = now_utc()
    window_start = now - _dt.timedelta(days=window_days)
    d30_start = now - _dt.timedelta(days=30)

    indexers = await client.indexers()
    all_stats = await client.stats()
    window_stats = await client.stats(window_start, now)
    d30_stats = await client.stats(d30_start, now)
    history, history_truncated = await client.history_grabs()

    return compute_report(
        indexers=indexers,
        all_stats=all_stats,
        window_stats=window_stats,
        d30_stats=d30_stats,
        history=history,
        window_days=window_days,
        generated_at=now,
        history_truncated=history_truncated,
    )
