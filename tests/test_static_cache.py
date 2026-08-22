"""Static assets must be revalidated, not served blind from a browser cache.

Starlette sends ETag/Last-Modified but no Cache-Control, and with no explicit
directive a browser applies *heuristic* freshness — it may reuse a cached file
without asking. After a UI upgrade that pairs a fresh index.html with a stale
app.js and renders a convincingly broken page (missing controls, previous
version's table headers) that looks like a failed deploy.

These exercise the mount directly rather than the full app, so no config, no
lifespan and no Prowlarr are involved.
"""
from __future__ import annotations

from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.testclient import TestClient

from app.main import STATIC_DIR, RevalidatingStaticFiles

client = TestClient(
    Starlette(routes=[Mount("/static", RevalidatingStaticFiles(directory=STATIC_DIR))])
)


def test_static_asset_is_served_with_no_cache():
    r = client.get("/static/app.js")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-cache"
    # Revalidation has to be cheap, so the validator must still be there.
    assert r.headers.get("etag")


def test_revalidation_returns_304_and_still_carries_the_directive():
    """The 304 is the steady state — if it dropped the header, the browser's
    stored directives would decay back to heuristic caching."""
    first = client.get("/static/app.js")
    again = client.get("/static/app.js", headers={"if-none-match": first.headers["etag"]})
    assert again.status_code == 304
    assert again.headers["cache-control"] == "no-cache"


def test_applies_to_every_asset_not_just_js():
    # A stale chart library or stylesheet breaks the page just as effectively.
    r = client.get("/static/chart.umd.min.js")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-cache"


def test_index_html_also_revalidates():
    """index.html and the script it loads have to move in lockstep — a fresh
    page pulling a cached script is exactly the broken-hybrid case."""
    import asyncio

    from app.main import index

    response = asyncio.run(index())
    assert response.headers["cache-control"] == "no-cache"
