"""FastAPI service: background-refreshed Prowlarr indexer report + live UI.

A single background task re-queries Prowlarr every ``REFRESH_INTERVAL_MINUTES``
and caches the computed report. The UI (served at ``/``) polls ``/api/data`` and
re-renders, so the page stays live without a reload.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import Config, load_config
from app.prowlarr import ProwlarrClient, build_report, iso, now_utc

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
)
# httpx logs every request at INFO (noisy: one line per Prowlarr call per refresh).
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("prowlarr-indexer-report")

STATIC_DIR = Path(__file__).parent / "static"


def _window_label(days: int | None) -> str:
    return "all" if days is None else f"{days}d"


# Assets must be revalidated on every load, never served blind from cache.
CACHE_CONTROL = "no-cache"


class RevalidatingStaticFiles(StaticFiles):
    """Static assets that must be revalidated rather than heuristically cached.

    Starlette sends ``ETag``/``Last-Modified`` but no ``Cache-Control``. With no
    explicit directive a browser falls back to *heuristic* freshness (a fraction
    of the time since Last-Modified) and may reuse a cached file without asking.
    After an upgrade that pairs a fresh ``index.html`` with a stale ``app.js``,
    which renders a convincingly broken UI — controls that don't appear, table
    headers from the previous version — and reads as a bad deploy even though
    the server is serving the new asset correctly.

    ``no-cache`` means "you may store it, but revalidate before using it", so the
    ETag still makes the steady state a tiny 304 rather than a re-download. The
    header is applied to the 304 as well, since that is what refreshes the
    browser's stored directives for next time.
    """

    def file_response(self, *args: Any, **kwargs: Any) -> Response:
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = CACHE_CONTROL
        return response


class State:
    """Holds the latest report + refresh bookkeeping."""

    def __init__(self) -> None:
        self.config: Config | None = None
        self.client: ProwlarrClient | None = None
        self.data: dict | None = None
        self.last_success: str | None = None
        self.last_error: str | None = None
        self.refreshing: bool = False

    async def refresh(self) -> None:
        if self.client is None or self.config is None or self.refreshing:
            return
        self.refreshing = True
        try:
            self.data = await build_report(
                self.client,
                list(self.config.window_options),
                self.config.default_window_days,
            )
            self.last_success = self.data["generatedAt"]
            self.last_error = None
            log.info(
                "refreshed: %d indexers, %d grabs",
                self.data["summary"]["indexers"],
                self.data["summary"]["totalGrabs"],
            )
        except Exception as exc:  # noqa: BLE001 — surface any fetch failure to the UI
            self.last_error = f"{type(exc).__name__}: {exc}"
            log.warning("refresh failed: %s", self.last_error)
        finally:
            self.refreshing = False


state = State()


async def _refresh_loop(interval_seconds: int) -> None:
    # Refresh first (priming the cache), then sleep — so the first fetch starts
    # immediately but does NOT block the app from serving (a full Prowlarr fetch
    # can take ~30-60s; the UI shows a "loading" state until /api/data is ready).
    while True:
        await state.refresh()
        await asyncio.sleep(interval_seconds)


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = load_config()
    state.config = cfg
    state.client = ProwlarrClient(cfg.prowlarr_url, cfg.api_key)
    log.info(
        "starting: prowlarr=%s window=%s of %s refresh=%dmin",
        cfg.prowlarr_url,
        _window_label(cfg.default_window_days),
        ",".join(_window_label(d) for d in cfg.window_options),
        cfg.refresh_interval_minutes,
    )
    task = asyncio.create_task(_refresh_loop(cfg.refresh_interval_seconds))
    try:
        yield
    finally:
        task.cancel()
        if state.client is not None:
            await state.client.aclose()


app = FastAPI(title="prowlarr-indexer-report", lifespan=lifespan)
app.mount("/static", RevalidatingStaticFiles(directory=STATIC_DIR), name="static")


@app.get("/healthz")
async def healthz() -> JSONResponse:
    """Healthy once the app is up. Reports staleness without failing the check.

    The container healthcheck only cares that the process is serving; a
    transient Prowlarr outage shouldn't flap the container.
    """
    ok = state.data is not None
    return JSONResponse(
        status_code=200,
        content={
            "status": "ok" if ok else "starting",
            "lastSuccess": state.last_success,
            "lastError": state.last_error,
        },
    )


@app.get("/api/data")
async def api_data() -> Response:
    if state.data is None:
        return JSONResponse(
            status_code=503,
            content={"status": "loading", "error": state.last_error},
        )
    payload = dict(state.data)
    payload["fetchedAt"] = iso(now_utc())
    payload["refreshIntervalMinutes"] = (
        state.config.refresh_interval_minutes if state.config else None
    )
    payload["prowlarrUrl"] = state.config.prowlarr_public_url if state.config else ""
    payload["lastError"] = state.last_error
    return JSONResponse(content=payload)


@app.post("/api/refresh")
async def api_refresh() -> JSONResponse:
    """Trigger an out-of-band refresh (the UI's manual refresh button)."""
    await state.refresh()
    return JSONResponse(
        content={"ok": state.last_error is None, "lastSuccess": state.last_success,
                 "lastError": state.last_error}
    )


@app.get("/")
async def index() -> FileResponse:
    # Same revalidate-before-use rule as /static (see RevalidatingStaticFiles):
    # the page and the script it loads have to move in lockstep.
    return FileResponse(
        STATIC_DIR / "index.html", headers={"Cache-Control": CACHE_CONTROL}
    )


def main() -> None:
    import uvicorn

    cfg = load_config()
    uvicorn.run("app.main:app", host=cfg.host, port=cfg.port, log_level="info")


if __name__ == "__main__":
    main()
