"""Runtime configuration, read from environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass

# Windows offered in the UI picker when WINDOW_OPTIONS is unset. ``None`` = all
# retained history. Kept modest: every extra window costs one indexerstats call
# per refresh, and more than a handful turns the picker into a menu.
DEFAULT_WINDOW_OPTIONS: tuple[int | None, ...] = (7, 30, 90, 180, 365, None)

# Values that select "all retained history" rather than a day count.
_ALL_TOKENS = {"all", "all-time", "alltime", "full", "full-history", "0"}


@dataclass(frozen=True)
class Config:
    prowlarr_url: str
    prowlarr_public_url: str
    api_key: str
    # Window selected when the page first loads. ``None`` = all retained history.
    default_window_days: int | None
    # Every window the UI offers; ``None`` = all retained history. Always
    # contains ``default_window_days``.
    window_options: tuple[int | None, ...]
    refresh_interval_minutes: int
    host: str
    port: int

    @property
    def refresh_interval_seconds(self) -> int:
        return self.refresh_interval_minutes * 60


def _int_env(name: str, default: int, *, minimum: int = 1) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        val = int(raw)
    except ValueError as exc:
        raise SystemExit(f"{name} must be an integer, got {raw!r}") from exc
    return max(minimum, val)


def _parse_window(name: str, raw: str) -> int | None:
    """One window token -> day count, or ``None`` for all retained history."""
    token = raw.strip().lower()
    if token in _ALL_TOKENS:
        return None
    try:
        days = int(token)
    except ValueError as exc:
        raise SystemExit(
            f"{name} accepts a number of days or 'all', got {raw.strip()!r}"
        ) from exc
    if days < 1:
        raise SystemExit(f"{name} must be at least 1 day (or 'all'), got {days}")
    return days


def _sort_key(days: int | None) -> tuple[int, int]:
    # All-time sorts last; day counts ascending.
    return (1, 0) if days is None else (0, days)


def load_window_options(default_days: int | None) -> tuple[int | None, ...]:
    """The set of windows the UI offers, ascending with all-time last.

    ``WINDOW_DAYS`` is always included — it is the initial selection, so it has
    to be one of the choices even if ``WINDOW_OPTIONS`` omits it.
    """
    raw = os.environ.get("WINDOW_OPTIONS", "").strip()
    if raw:
        parsed = [_parse_window("WINDOW_OPTIONS", part) for part in raw.split(",") if part.strip()]
        if not parsed:
            raise SystemExit("WINDOW_OPTIONS is set but empty")
    else:
        parsed = list(DEFAULT_WINDOW_OPTIONS)
    if default_days not in parsed:
        parsed.append(default_days)
    return tuple(sorted(set(parsed), key=_sort_key))


def load_config() -> Config:
    api_key = os.environ.get("PROWLARR_API_KEY", "").strip()
    if not api_key:
        raise SystemExit(
            "PROWLARR_API_KEY is required. Set it in the environment "
            "(see .env.example)."
        )
    raw_window = os.environ.get("WINDOW_DAYS", "").strip()
    default_window = _parse_window("WINDOW_DAYS", raw_window) if raw_window else 90
    # The browser-facing Prowlarr URL, used only to deep-link from the report to
    # Prowlarr. It often differs from PROWLARR_URL: the server may reach Prowlarr
    # at a Docker-internal host (http://prowlarr:9696) the user's browser can't
    # resolve. Opt-in — when unset, the report shows no "Open Prowlarr" links.
    return Config(
        prowlarr_url=os.environ.get("PROWLARR_URL", "http://localhost:9696").rstrip("/"),
        prowlarr_public_url=os.environ.get("PROWLARR_PUBLIC_URL", "").strip().rstrip("/"),
        api_key=api_key,
        default_window_days=default_window,
        window_options=load_window_options(default_window),
        refresh_interval_minutes=_int_env("REFRESH_INTERVAL_MINUTES", 15),
        host=os.environ.get("HOST", "0.0.0.0"),
        port=_int_env("PORT", 8787, minimum=1),
    )
