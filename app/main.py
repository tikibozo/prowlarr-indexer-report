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
            self.data = await build_report(self.client, self.config.window_days)
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
        "starting: prowlarr=%s window=%dd refresh=%dmin",
        cfg.prowlarr_url,
        cfg.window_days,
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
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


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
    return FileResponse(STATIC_DIR / "index.html")


def main() -> None:
    import uvicorn

    cfg = load_config()
    uvicorn.run("app.main:app", host=cfg.host, port=cfg.port, log_level="info")


if __name__ == "__main__":
    main()
