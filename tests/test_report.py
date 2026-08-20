import datetime as _dt

import pytest

from app.config import load_window_options
from app.prowlarr import (
    build_report,
    compute_report,
    normalize_source,
    window_meta,
)

NOW = _dt.datetime(2026, 6, 8, 12, 0, 0, tzinfo=_dt.UTC)

# Profile 1 = auto-search on; profile 2 = manual/interactive-only (auto off).
APP_PROFILES = [
    {"id": 1, "name": "Auto", "enableAutomaticSearch": True},
    {"id": 2, "name": "Manual", "enableAutomaticSearch": False},
]

INDEXERS = [
    {"id": 1, "name": "DrunkenSlug", "protocol": "usenet", "enable": True, "priority": 10,
     "appProfileId": 1},
    {"id": 2, "name": "DeadTracker", "protocol": "torrent", "enable": True, "priority": 25,
     "appProfileId": 1},
    {"id": 3, "name": "HighCost", "protocol": "torrent", "enable": True, "priority": 25,
     "appProfileId": 1},
    {"id": 4, "name": "ColdOne", "protocol": "usenet", "enable": True, "priority": 25,
     "appProfileId": 1},
    {"id": 5, "name": "OffNever", "protocol": "torrent", "enable": False, "priority": 50,
     "appProfileId": 1},
    # Manual-only profile, zero grabs — should be neutral "manual", NOT "remove".
    {"id": 6, "name": "ManualOnly", "protocol": "torrent", "enable": True, "priority": 25,
     "appProfileId": 2},
]

ALL_STATS = [
    {"indexerId": 1, "numberOfQueries": 1000, "numberOfGrabs": 500,
     "numberOfFailedQueries": 10, "averageResponseTime": 300},
    {"indexerId": 2, "numberOfQueries": 800, "numberOfGrabs": 0, "numberOfFailedQueries": 0},
    {"indexerId": 3, "numberOfQueries": 9000, "numberOfGrabs": 20, "numberOfFailedQueries": 5},
    {"indexerId": 4, "numberOfQueries": 2000, "numberOfGrabs": 40, "numberOfFailedQueries": 0},
    {"indexerId": 5, "numberOfQueries": 0, "numberOfGrabs": 0, "numberOfFailedQueries": 0},
    {"indexerId": 6, "numberOfQueries": 300, "numberOfGrabs": 0, "numberOfFailedQueries": 0},
]

WINDOWS = [7, 30, 90, None]


def _at(days_ago: int) -> str:
    """A history timestamp `days_ago` before NOW."""
    return (NOW - _dt.timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")

HISTORY = [
    # indexer 1: grabs inside 7d, inside 30d, and inside 90d only
    {"indexerId": 1, "date": _at(2), "data": {"source": "Sonarr"}},
    {"indexerId": 1, "date": _at(19), "data": {"source": "Radarr"}},
    {"indexerId": 1, "date": _at(60), "data": {"source": "Sonarr"}},
    # indexer 3: last grab inside 90d but outside 30d -> cold on the tighter windows
    {"indexerId": 3, "date": _at(45), "data": {"source": "sonarr (4k)"}},
    # indexer 4: long cold, outside every finite window
    {"indexerId": 4, "date": _at(144), "data": {"source": "Lidarr"}},
]


def _report(**over):
    kwargs = dict(
        indexers=INDEXERS, all_stats=ALL_STATS, history=HISTORY,
        windows=WINDOWS, window_days=90, generated_at=NOW,
        app_profiles=APP_PROFILES,
    )
    kwargs.update(over)
    return compute_report(**kwargs)


def _by_name(report):
    return {r["name"]: r for r in report["indexers"]}


def test_summary_counts():
    r = _report()
    s = r["summary"]
    assert s["indexers"] == 6
    assert s["enabled"] == 5
    assert s["totalGrabs"] == 560  # 500 + 0 + 20 + 40 + 0 + 0
    assert s["manual"] == 1
    assert r["windowDays"] == 90


def test_sorted_by_grabs_desc():
    names = [r["name"] for r in _report()["indexers"]]
    assert names[0] == "DrunkenSlug"  # 500 grabs, highest


def test_remove_flag_never_grabbed():
    row = _by_name(_report())["DeadTracker"]
    assert row["flag"] == "remove"
    assert "Never grabbed" in row["reason"]


def test_remove_flag_went_cold_uses_last_grab_date():
    row = _by_name(_report())["ColdOne"]
    assert row["flag"] == "remove"
    assert "No grabs in 90d" in row["reason"]
    assert "2026-01-15" in row["reason"]


def test_watch_flag_high_cost_low_yield():
    row = _by_name(_report())["HighCost"]  # 9000 queries, 20 grabs -> 0.22%
    assert row["flag"] == "watch"


def test_manual_profile_indexer_is_neutral_not_remove():
    row = _by_name(_report())["ManualOnly"]
    assert row["flag"] == "manual"          # neutral, despite 0 grabs
    assert row["autoSearch"] is False
    assert row["appProfile"] == "Manual"
    assert "automatic search off" in row["reason"]


def test_manual_indexers_excluded_from_remove():
    r = _report()
    removes = [x["name"] for x in r["indexers"] if x["flag"] == "remove"]
    assert "ManualOnly" not in removes
    # only auto-search indexers can be remove candidates
    assert all(x["autoSearch"] for x in r["indexers"] if x["flag"] == "remove")


def test_missing_profile_defaults_to_auto():
    # No app_profiles passed -> every indexer treated as auto-search (back-compat).
    r = _report(app_profiles=None)
    row = _by_name(r)["ManualOnly"]
    assert row["autoSearch"] is True
    assert row["flag"] == "remove"  # 0 grabs, now treated as auto


def test_disabled_never_grabbed_flag():
    row = _by_name(_report())["OffNever"]
    assert row["flag"] == "disabled"
    assert row["enabled"] is False


def test_productive_indexer_unflagged():
    row = _by_name(_report())["DrunkenSlug"]
    assert row["flag"] == ""
    assert row["grabRate"] == 50.0  # 500/1000
    assert row["failRate"] == 1.0   # 10/1000


def test_per_app_breakdown_and_apps_list():
    r = _report()
    row = _by_name(r)["DrunkenSlug"]
    assert row["perApp"] == {"Sonarr": 2, "Radarr": 1}
    # "sonarr (4k)" normalizes onto Sonarr
    assert _by_name(r)["HighCost"]["perApp"] == {"Sonarr": 1}
    assert set(r["apps"]) == {"Sonarr", "Radarr", "Lidarr"}


def test_per_app_sum_matches_history_total():
    r = _report()
    per_app_total = sum(sum(row["perApp"].values()) for row in r["indexers"])
    assert per_app_total == len(HISTORY)


def test_timeline_monthly_buckets():
    tl = dict(_report()["timeline"])
    assert tl["2026-06"] == 1          # indexer 1, 2 days ago
    assert tl["2026-05"] == 1          # indexer 1, 19 days ago
    assert tl["2026-04"] == 2          # indexer 1 (60d) + indexer 3 (45d)
    assert tl["2026-01"] == 1          # indexer 4, long cold


def test_history_span_reflects_full_retained_range():
    h = _report()["history"]
    assert h["start"] == _at(144)[:10]  # oldest grab in HISTORY
    assert h["end"] == _at(2)[:10]      # newest grab in HISTORY
    assert h["spanDays"] == 142         # 144 days ago .. 2 days ago
    assert h["truncated"] is False


def test_history_truncated_flag_passthrough():
    assert _report(history_truncated=True)["history"]["truncated"] is True


def test_normalize_source():
    assert normalize_source("Sonarr") == "Sonarr"
    assert normalize_source("radarr (4k)") == "Radarr"
    assert normalize_source(None) == "Other"
    assert normalize_source("Mylar") == "Mylar"


# ---- Configurable time window --------------------------------------------

def test_windows_metadata_and_default_key():
    r = _report()
    assert [w["key"] for w in r["windows"]] == ["7", "30", "90", "all"]
    assert [w["short"] for w in r["windows"]] == ["7d", "30d", "90d", "All time"]
    assert r["defaultWindow"] == "90"
    assert r["windowDays"] == 90


def test_every_row_carries_a_verdict_per_window():
    for row in _report()["indexers"]:
        assert set(row["byWindow"]) == {"7", "30", "90", "all"}
        for w in row["byWindow"].values():
            assert set(w) == {"grabs", "flag", "reason"}


def test_top_level_fields_mirror_the_default_window():
    for row in _report()["indexers"]:
        sel = row["byWindow"]["90"]
        assert (row["grabsWin"], row["flag"], row["reason"]) == (
            sel["grabs"], sel["flag"], sel["reason"])


def test_all_time_window_uses_total_grabs():
    # All-time stays the authoritative indexerstats total (so a truncated history
    # walk can't move it); the finite windows are counted out of history.
    row = _by_name(_report())["DrunkenSlug"]
    assert row["byWindow"]["all"]["grabs"] == row["grabsAll"] == 500
    assert row["byWindow"]["90"]["grabs"] == 3
    assert row["byWindow"]["30"]["grabs"] == 2
    assert row["byWindow"]["7"]["grabs"] == 1


def test_cold_indexer_is_not_a_removal_candidate_at_all_time():
    # ColdOne last grabbed in January: cold over 90d, but it *has* grabbed, so
    # over all retained history it is simply a low performer, not dead weight.
    row = _by_name(_report())["ColdOne"]
    assert row["byWindow"]["90"]["flag"] == "remove"
    assert row["byWindow"]["all"]["flag"] == ""


def test_all_time_never_reports_a_cold_reason():
    # "No grabs in <window>" is unreachable at all-time — an indexer with zero
    # grabs there is reported as never having grabbed at all.
    for row in _report()["indexers"]:
        assert "No grabs in" not in row["byWindow"]["all"]["reason"]
    dead = _by_name(_report())["DeadTracker"]
    assert dead["byWindow"]["all"]["flag"] == "remove"
    assert "Never grabbed" in dead["byWindow"]["all"]["reason"]


def test_narrow_window_reports_its_own_span_in_the_reason():
    row = _by_name(_report())["HighCost"]
    assert row["byWindow"]["7"]["flag"] == "remove"
    assert "No grabs in 7d" in row["byWindow"]["7"]["reason"]
    assert row["byWindow"]["90"]["flag"] == "watch"   # still grabbing over 90d


def test_summary_per_window_tracks_the_verdicts():
    s = _report()["summaryByWindow"]
    assert s["7"]["removeCandidates"] == 3
    assert s["90"]["removeCandidates"] == 2
    assert s["all"]["removeCandidates"] == 1
    assert s["all"]["watchCandidates"] == 1
    assert s["7"]["watchCandidates"] == 0
    # window-independent facts stay put
    assert {v["indexers"] for v in s.values()} == {6}
    assert {v["manual"] for v in s.values()} == {1}
    assert _report()["summary"] == s["90"]


def test_summary_window_grabs():
    s = _report()["summaryByWindow"]
    assert s["all"]["windowGrabs"] == 560   # every grab ever, per indexerstats
    assert s["90"]["windowGrabs"] == 4      # 3 (indexer 1) + 1 (indexer 3)
    assert s["7"]["windowGrabs"] == 1


def test_grabs30_column_is_independent_of_the_selected_window():
    r = _report(window_days=7)
    assert r["defaultWindow"] == "7"
    row = _by_name(r)["DrunkenSlug"]
    assert row["grabsWin"] == 1    # follows the selection (7d)
    assert row["grabs30"] == 2     # fixed 30d column, unchanged


def test_default_window_is_added_when_missing_from_the_options():
    r = _report(windows=[7, 30], window_days=90)
    assert [w["key"] for w in r["windows"]] == ["7", "30", "90"]
    assert r["defaultWindow"] == "90"


def test_all_time_default_window():
    r = _report(window_days=None)
    assert r["defaultWindow"] == "all"
    assert r["windowDays"] is None
    assert _by_name(r)["ColdOne"]["flag"] == ""


@pytest.mark.parametrize("days,short,label", [
    (7, "7d", "the last 7 days"),
    (30, "30d", "the last 30 days"),
    (90, "90d", "the last 3 months"),
    (180, "180d", "the last 6 months"),
    (365, "365d", "the last year"),
    (730, "730d", "the last 2 years"),
    (None, "All time", "all retained history"),
])
def test_window_meta_labels(days, short, label):
    m = window_meta(days)
    assert (m["short"], m["label"], m["days"]) == (short, label, days)


# ---- WINDOW_OPTIONS parsing ----------------------------------------------

def test_window_options_default(monkeypatch):
    monkeypatch.delenv("WINDOW_OPTIONS", raising=False)
    assert load_window_options(90) == (7, 30, 90, 180, 365, None)


def test_window_options_custom_sorted_with_all_time_last(monkeypatch):
    monkeypatch.setenv("WINDOW_OPTIONS", "all, 90 ,14,90")
    assert load_window_options(90) == (14, 90, None)


def test_window_options_always_include_the_default(monkeypatch):
    monkeypatch.setenv("WINDOW_OPTIONS", "7,30")
    assert load_window_options(60) == (7, 30, 60)
    assert load_window_options(None) == (7, 30, None)


def test_window_options_reject_garbage(monkeypatch):
    monkeypatch.setenv("WINDOW_OPTIONS", "7,soon")
    with pytest.raises(SystemExit):
        load_window_options(90)
    monkeypatch.setenv("WINDOW_OPTIONS", "7,-3")
    with pytest.raises(SystemExit):
        load_window_options(90)


# ---- API cost -------------------------------------------------------------

def test_build_report_makes_exactly_one_indexerstats_call():
    """The performance guard, not a style preference.

    ``indexerstats`` aggregates Prowlarr's whole History table — measured at 57s
    against a 3.1M-row instance, and it scales with the window — so one call per
    configured window is what made refreshes time out. Windowed grabs come from
    the history walk instead, which is why this must stay at one call no matter
    how many windows are configured.
    """
    import asyncio

    calls: list[dict | None] = []

    class Stub:
        async def indexers(self):
            return INDEXERS

        async def app_profiles(self):
            return APP_PROFILES

        async def stats(self, start=None, end=None):
            calls.append(None if start is None else {"start": start, "end": end})
            return ALL_STATS

        async def history_grabs(self):
            # build_report stamps wall-clock time, so this history has to be
            # dated against wall-clock too (not the frozen NOW the other tests use).
            real_now = _dt.datetime.now(_dt.UTC)

            def at(d):
                return (real_now - _dt.timedelta(days=d)).strftime("%Y-%m-%dT%H:%M:%SZ")

            return [
                {"indexerId": 1, "date": at(2), "data": {"source": "Sonarr"}},
                {"indexerId": 1, "date": at(19), "data": {"source": "Radarr"}},
                {"indexerId": 1, "date": at(60), "data": {"source": "Sonarr"}},
            ], False

    report = asyncio.run(build_report(Stub(), [7, 30, 90, 180, 365, None], 90))

    assert len(calls) == 1, f"expected 1 indexerstats call, got {len(calls)}"
    assert calls == [None], "the single call must be unwindowed (all-time)"
    # ...and the windows are still fully judged despite no windowed fetch.
    assert [w["key"] for w in report["windows"]] == ["7", "30", "90", "180", "365", "all"]
    assert _by_name(report)["DrunkenSlug"]["byWindow"]["30"]["grabs"] == 2
