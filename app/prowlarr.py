"""Prowlarr API client and report computation.

The data layer is split in two so the analysis is trivially testable:

  * ``ProwlarrClient`` does the (async) HTTP I/O against the Prowlarr v1 API.
  * ``compute_report`` is a pure function over already-fetched payloads.

Data sources (all read-only):
  * GET /api/v1/indexer        — name, protocol, enable, priority
  * GET /api/v1/indexerstats   — per-indexer aggregates. Called ONCE, unwindowed,
                                 for the all-time queries / failures / latency.
                                 It accepts ?startDate=&endDate=, but we do NOT
                                 use that: indexerstats aggregates the whole
                                 History table, which is ~99% query events, so a
                                 single call costs tens of seconds on a real
                                 instance (57s against a 3.1M-row table) and
                                 scales with the window. Windowed grab counts are
                                 derived from the grab history below instead —
                                 verified to match indexerstats exactly, and free.
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


# A window is a number of days, or ``None`` for "all retained history". The key
# is what the UI and the JSON payload index windowed results by.
ALL_TIME = "all"


def window_key(days: int | None) -> str:
    return ALL_TIME if days is None else str(days)


def window_meta(days: int | None) -> dict:
    """UI-facing description of one window: button text + spoken label."""
    if days is None:
        return {"key": ALL_TIME, "days": None, "short": "All time",
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


class ProwlarrClient:
    # 60s was too tight: a single unwindowed indexerstats call measured 57s on a
    # real instance (3.1M history rows), so refreshes failed ~40% of the time.
    def __init__(self, base_url: str, api_key: str, *, timeout: float = 300.0) -> None:
        self._base = base_url.rstrip("/")
        self._timeout = timeout
        self._client = httpx.AsyncClient(
            base_url=self._base,
            headers={"X-Api-Key": api_key},
            timeout=timeout,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        try:
            resp = await self._client.get(path, params=params)
        except httpx.TimeoutException as exc:
            # httpx timeouts stringify to "" — name the endpoint so the UI banner
            # says which Prowlarr call is slow instead of a bare "ReadTimeout: ".
            raise TimeoutError(
                f"{type(exc).__name__} after {self._timeout:g}s on {path}"
            ) from exc
        resp.raise_for_status()
        return resp.json()

    async def indexers(self) -> list[dict]:
        return await self._get("/api/v1/indexer")

    async def app_profiles(self) -> list[dict]:
        """App Sync Profiles — carry enableAutomaticSearch / Rss / Interactive.

        Each indexer references one via ``appProfileId``; a profile with
        ``enableAutomaticSearch == false`` means the indexer is only used for
        manual/interactive search, so zero automated grabs is expected, not a
        sign it's useless.
        """
        return await self._get("/api/v1/appprofile")

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


def _verdict(
    *,
    enabled: bool,
    auto_search: bool,
    profile_name: str,
    grabs_all: int,
    grabs_win: int,
    queries: int,
    grab_rate: float,
    window_short: str,
    last: str,
) -> tuple[str, str]:
    """The flag + reason for one indexer, judged inside one window.

    Flag precedence: disabled > manual (neutral) > remove/watch. Only auto-search
    indexers are eligible for remove/watch — a manual/interactive-only profile is
    *expected* to have no automated grabs, so it gets the neutral "manual" tag
    instead of being called dead weight.

    Only the "gone cold" branch is window-dependent, and on the all-time window
    it is unreachable by construction (``grabs_win == grabs_all``), so an
    indexer is never called cold over the same span that says it never grabbed.
    """
    if not enabled:
        return ("disabled", "Already disabled, never grabbed") if grabs_all == 0 else ("", "")
    if not auto_search:
        return "manual", (
            f"Manual/interactive-only profile ({profile_name}) — automatic search off"
        )
    if grabs_all == 0:
        return "remove", f"Never grabbed anything ({queries} queries)"
    if grabs_win == 0:
        return "remove", f"No grabs in {window_short} (last: {last or 'unknown'})"
    if queries >= 5000 and grab_rate < 0.005:
        return "watch", f"High cost: {queries} queries, {grab_rate * 100:.2f}% grab rate"
    return "", ""


def compute_report(
    *,
    indexers: list[dict],
    all_stats: list[dict],
    history: list[dict],
    windows: list[int | None],
    window_days: int | None,
    generated_at: _dt.datetime,
    history_truncated: bool = False,
    app_profiles: list[dict] | None = None,
) -> dict:
    """Pure transform of raw Prowlarr payloads into the report data model.

    Every configured window is judged, not just the default one: each indexer
    carries a ``byWindow`` block (grabs + flag + reason) and there is a summary
    per window. The UI picks one and can switch instantly, because the verdict
    for every window is already in the payload.

    Windowed grab counts are counted out of ``history`` rather than fetched from
    a windowed ``indexerstats`` call per window. Prowlarr derives both from the
    same History table, so the numbers are identical (checked per-indexer over
    7/30/90d against a live instance: exact match), but counting locally costs
    nothing while each windowed API call costs seconds-to-a-minute. That is what
    makes an arbitrary set of windows affordable.

    All-time grabs still come from ``all_stats``, so a truncated history page
    walk can never inflate or deflate the headline total.
    """
    metas = [window_meta(d) for d in windows]
    if not metas:  # defensive: a window-less report has nothing to judge
        metas = [window_meta(window_days)]
    default_key = window_key(window_days)
    if all(m["key"] != default_key for m in metas):
        metas.append(window_meta(window_days))
        metas.sort(key=lambda m: (1, 0) if m["days"] is None else (0, m["days"]))

    all_by = _stats_by_id(all_stats)

    # Cutoffs for every finite window, plus the fixed 30d column. Dates are
    # compared as ISO-8601 Z strings, which sort lexicographically — the same
    # idiom the last-grab/month bucketing below already relies on.
    def _cutoff(days: int) -> str:
        return iso(generated_at - _dt.timedelta(days=days))

    cutoffs = [(m["key"], _cutoff(m["days"])) for m in metas if m["days"] is not None]
    d30_cutoff = _cutoff(30)
    win_counts: dict[int, dict[str, int]] = {}
    d30_counts: dict[int, int] = {}

    # appProfileId -> (auto-search enabled?, profile name). Missing profile
    # defaults to auto=True so we never hide a real auto indexer behind "manual".
    prof_auto: dict[int, bool] = {}
    prof_name: dict[int, str] = {}
    for p in app_profiles or []:
        prof_auto[p["id"]] = bool(p.get("enableAutomaticSearch", True))
        prof_name[p["id"]] = p.get("name", "")

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
            for key, cut in cutoffs:
                if date >= cut:
                    bucket = win_counts.setdefault(iid, {})
                    bucket[key] = bucket.get(key, 0) + 1
            if date >= d30_cutoff:
                d30_counts[iid] = d30_counts.get(iid, 0) + 1
            if iid not in last_grab or date > last_grab[iid]:
                last_grab[iid] = date
            if earliest_grab is None or date < earliest_grab:
                earliest_grab = date
            if latest_grab is None or date > latest_grab:
                latest_grab = date

    rows: list[dict] = []
    for ix in indexers:
        iid = ix["id"]
        a = all_by.get(iid, {})
        queries = a.get("numberOfQueries", 0) or 0
        grabs_all = a.get("numberOfGrabs", 0) or 0
        failed_q = a.get("numberOfFailedQueries", 0) or 0
        grab_rate = (grabs_all / queries) if queries else 0.0
        fail_rate = (failed_q / queries) if queries else 0.0

        pid = ix.get("appProfileId")
        auto_search = prof_auto.get(pid, True)
        profile_name = prof_name.get(pid, "")
        enabled = bool(ix.get("enable", True))
        last = (last_grab.get(iid, "") or "")[:10]

        by_window: dict[str, dict] = {}
        for m in metas:
            # All-time is definitionally the whole of grabsAll, so it needs no
            # windowed stats row to be correct even if Prowlarr omits the indexer.
            grabs_win = (
                grabs_all if m["days"] is None
                else win_counts.get(iid, {}).get(m["key"], 0)
            )
            flag, reason = _verdict(
                enabled=enabled, auto_search=auto_search, profile_name=profile_name,
                grabs_all=grabs_all, grabs_win=grabs_win, queries=queries,
                grab_rate=grab_rate, window_short=m["short"], last=last,
            )
            by_window[m["key"]] = {"grabs": grabs_win, "flag": flag, "reason": reason}

        sel = by_window[default_key]
        rows.append(
            {
                "id": iid,
                "name": ix.get("name", "?"),
                "protocol": ix.get("protocol", "?"),
                "enabled": enabled,
                "priority": ix.get("priority", 25),
                "grabsAll": grabs_all,
                # grabsWin/flag/reason are the default window's verdict, kept at
                # the top level so /api/data stays readable for scripts that
                # don't care about window switching.
                "grabsWin": sel["grabs"],
                "grabs30": d30_counts.get(iid, 0),
                "queries": queries,
                "grabRate": round(grab_rate * 100, 3),
                "failRate": round(fail_rate * 100, 3),
                "respTime": a.get("averageResponseTime", 0) or 0,
                "grabRespTime": a.get("averageGrabResponseTime", 0) or 0,
                "lastGrab": last,
                "perApp": per_app.get(iid, {}),
                "autoSearch": auto_search,
                "appProfile": profile_name,
                "flag": sel["flag"],
                "reason": sel["reason"],
                "byWindow": by_window,
            }
        )

    rows.sort(key=lambda r: r["grabsAll"], reverse=True)

    def _summary(key: str) -> dict:
        return {
            "indexers": len(rows),
            "enabled": sum(1 for r in rows if r["enabled"]),
            "totalGrabs": sum(r["grabsAll"] for r in rows),
            "windowGrabs": sum(r["byWindow"][key]["grabs"] for r in rows),
            "removeCandidates": sum(1 for r in rows if r["byWindow"][key]["flag"] == "remove"),
            "watchCandidates": sum(1 for r in rows if r["byWindow"][key]["flag"] == "watch"),
            "manual": sum(1 for r in rows if r["byWindow"][key]["flag"] == "manual"),
        }

    summary_by_window = {m["key"]: _summary(m["key"]) for m in metas}
    span_days = None
    if earliest_grab and latest_grab:
        span_days = (_dt.datetime.fromisoformat(latest_grab.replace("Z", "+00:00"))
                     - _dt.datetime.fromisoformat(earliest_grab.replace("Z", "+00:00"))).days
    return {
        "generatedAt": iso(generated_at),
        "windowDays": window_days,
        "defaultWindow": default_key,
        "windows": metas,
        "summary": summary_by_window[default_key],
        "summaryByWindow": summary_by_window,
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


async def build_report(
    client: ProwlarrClient,
    windows: list[int | None],
    window_days: int | None,
) -> dict:
    """Fetch everything from Prowlarr and compute the report data model.

    Exactly one ``indexerstats`` call, regardless of how many windows are
    configured — windowed grab counts come out of the history walk instead (see
    ``compute_report``). Adding a window is therefore free at the API layer.
    """
    now = now_utc()

    indexers = await client.indexers()
    app_profiles = await client.app_profiles()
    all_stats = await client.stats()
    history, history_truncated = await client.history_grabs()

    return compute_report(
        indexers=indexers,
        all_stats=all_stats,
        history=history,
        windows=windows,
        window_days=window_days,
        generated_at=now,
        history_truncated=history_truncated,
        app_profiles=app_profiles,
    )
