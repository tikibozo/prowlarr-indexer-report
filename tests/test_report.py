import datetime as _dt

from app.prowlarr import compute_report, normalize_source

NOW = _dt.datetime(2026, 6, 8, 12, 0, 0, tzinfo=_dt.UTC)

INDEXERS = [
    {"id": 1, "name": "DrunkenSlug", "protocol": "usenet", "enable": True, "priority": 10},
    {"id": 2, "name": "DeadTracker", "protocol": "torrent", "enable": True, "priority": 25},
    {"id": 3, "name": "HighCost", "protocol": "torrent", "enable": True, "priority": 25},
    {"id": 4, "name": "ColdOne", "protocol": "usenet", "enable": True, "priority": 25},
    {"id": 5, "name": "OffNever", "protocol": "torrent", "enable": False, "priority": 50},
]

ALL_STATS = [
    {"indexerId": 1, "numberOfQueries": 1000, "numberOfGrabs": 500,
     "numberOfFailedQueries": 10, "averageResponseTime": 300},
    {"indexerId": 2, "numberOfQueries": 800, "numberOfGrabs": 0, "numberOfFailedQueries": 0},
    {"indexerId": 3, "numberOfQueries": 9000, "numberOfGrabs": 20, "numberOfFailedQueries": 5},
    {"indexerId": 4, "numberOfQueries": 2000, "numberOfGrabs": 40, "numberOfFailedQueries": 0},
    {"indexerId": 5, "numberOfQueries": 0, "numberOfGrabs": 0, "numberOfFailedQueries": 0},
]

# Window stats: indexer 4 went cold (0 grabs in window), others have recent grabs.
WINDOW_STATS = [
    {"indexerId": 1, "numberOfGrabs": 120},
    {"indexerId": 3, "numberOfGrabs": 3},
    {"indexerId": 4, "numberOfGrabs": 0},
]
D30_STATS = [{"indexerId": 1, "numberOfGrabs": 40}]

HISTORY = [
    {"indexerId": 1, "date": "2026-06-01T10:00:00Z", "data": {"source": "Sonarr"}},
    {"indexerId": 1, "date": "2026-05-20T10:00:00Z", "data": {"source": "Radarr"}},
    {"indexerId": 3, "date": "2026-06-02T10:00:00Z", "data": {"source": "sonarr (4k)"}},
    {"indexerId": 4, "date": "2026-01-15T10:00:00Z", "data": {"source": "Lidarr"}},
]


def _report():
    return compute_report(
        indexers=INDEXERS, all_stats=ALL_STATS, window_stats=WINDOW_STATS,
        d30_stats=D30_STATS, history=HISTORY, window_days=90, generated_at=NOW,
    )


def _by_name(report):
    return {r["name"]: r for r in report["indexers"]}


def test_summary_counts():
    r = _report()
    s = r["summary"]
    assert s["indexers"] == 5
    assert s["enabled"] == 4
    assert s["totalGrabs"] == 560  # 500 + 0 + 20 + 40 + 0
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
    assert row["perApp"] == {"Sonarr": 1, "Radarr": 1}
    # "sonarr (4k)" normalizes onto Sonarr
    assert _by_name(r)["HighCost"]["perApp"] == {"Sonarr": 1}
    assert set(r["apps"]) == {"Sonarr", "Radarr", "Lidarr"}


def test_per_app_sum_matches_history_total():
    r = _report()
    per_app_total = sum(sum(row["perApp"].values()) for row in r["indexers"])
    assert per_app_total == len(HISTORY)


def test_timeline_monthly_buckets():
    tl = dict(_report()["timeline"])
    assert tl["2026-06"] == 2
    assert tl["2026-05"] == 1
    assert tl["2026-01"] == 1


def test_history_span_reflects_full_retained_range():
    h = _report()["history"]
    assert h["start"] == "2026-01-15"  # oldest grab in HISTORY
    assert h["end"] == "2026-06-02"    # newest grab in HISTORY
    assert h["spanDays"] == 138
    assert h["truncated"] is False


def test_history_truncated_flag_passthrough():
    r = compute_report(
        indexers=INDEXERS, all_stats=ALL_STATS, window_stats=WINDOW_STATS,
        d30_stats=D30_STATS, history=HISTORY, window_days=90, generated_at=NOW,
        history_truncated=True,
    )
    assert r["history"]["truncated"] is True


def test_normalize_source():
    assert normalize_source("Sonarr") == "Sonarr"
    assert normalize_source("radarr (4k)") == "Radarr"
    assert normalize_source(None) == "Other"
    assert normalize_source("Mylar") == "Mylar"
