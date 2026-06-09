"""Runtime configuration, read from environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    prowlarr_url: str
    api_key: str
    window_days: int
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


def load_config() -> Config:
    api_key = os.environ.get("PROWLARR_API_KEY", "").strip()
    if not api_key:
        raise SystemExit(
            "PROWLARR_API_KEY is required. Set it in the environment "
            "(see .env.example)."
        )
    return Config(
        prowlarr_url=os.environ.get("PROWLARR_URL", "http://localhost:9696").rstrip("/"),
        api_key=api_key,
        window_days=_int_env("WINDOW_DAYS", 90),
        refresh_interval_minutes=_int_env("REFRESH_INTERVAL_MINUTES", 15),
        host=os.environ.get("HOST", "0.0.0.0"),
        port=_int_env("PORT", 8787, minimum=1),
    )
