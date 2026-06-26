# prowlarr-indexer-report

A small live web service that turns Prowlarr's thin built-in stats into a
report you can act on: it ranks every indexer by **grabs**, shows **recent
trend**, exposes **query cost / failure / latency**, breaks grabs down by the
**consuming app** (Sonarr/Radarr/Lidarr/…), and **flags indexers that are safe
to disable** — so you can tell which of your indexers actually earn their keep.

The page is live: a background task re-queries Prowlarr on an interval and the
UI polls for the latest snapshot, so charts stay current without a reload.

![Prowlarr Indexer Usefulness Report — a verdict-first dark dashboard: summary cards with remove/watch/manual counts, a "verdict" panel listing the indexers safe to disable with the reason for each, a filterable sortable table of every indexer, and a collapsible Analysis section (grabs by indexer, recent trend, efficiency scatter, per-app source breakdown, grabs-over-time). Shown with demo data; indexer names are fictional.](docs/report.png)

## How it works

```
Prowlarr v1 API ──(every REFRESH_INTERVAL_MINUTES)──► background refresh
   ├─ GET /api/v1/indexer        (name, protocol, enable, priority)
   ├─ GET /api/v1/indexerstats   (grabs/queries/fails, all-time + 90d + 30d)
   └─ GET /api/v1/history        (per-grab events → per-app split + timeline)
                                          │
                                   cached report
                                          │
   browser ◄── GET /api/data (polled) ◄── FastAPI ── GET / (UI), /healthz
```

All Prowlarr calls are **read-only**. Grab counts (all-time / window / 30d) come
straight from `indexerstats`, which accepts `startDate`/`endDate`. The per-app
breakdown and the monthly timeline are reconstructed from grab history (the only
endpoint that records which app consumed each grab).

### History coverage

The report shows the **full grab history Prowlarr retains** — every page of
`/api/v1/history` is read (no client-side cap in practice), and `indexerstats`
totals match it because Prowlarr derives both from the same History table.
Prowlarr prunes that table via its **History Cleanup** setting
(`historycleanupdays`, **default 30 days** — unlike Sonarr/Radarr, which default
to 365). A cleanup task runs every 24h and deletes history older than that many
days (set it to `0` to keep history forever). So "all-time" really means "all
retained history": on a default Prowlarr that's only the last ~30 days, and once
an instance is older than the configured window the oldest day rolls off daily.
To change it, open the **History** page and click **Options** in the top-right
toolbar (it's there, not under Settings → General). The header shows the actual
span (`full history since <date>`), and a banner warns if paging ever hits its
safety cap so nothing is silently dropped.

### Flags

Each enabled indexer gets at most one flag, in priority order:

- **manual** _(neutral)_ — the indexer's [App Sync Profile](https://wiki.servarr.com/prowlarr/settings#app-profiles)
  has **Automatic Search off** (manual/interactive-only). Zero automated grabs is
  *expected* here, so these are never called dead weight — they're broken out so
  the remove/watch heuristics don't fire on them.
- **remove** — an **auto-search** indexer that never grabbed anything (pure query
  cost) or has no grabs within the recent window (gone cold; last-grab date shown).
- **watch** — an **auto-search** indexer with high query volume (≥5000) but a grab
  rate under 0.5% (lots of cost for little return).

Only auto-search indexers are eligible for **remove**/**watch**, since those are
the ones expected to produce automated grabs. Disabled indexers that never grabbed
are noted (**disabled**) but not counted as candidates. The per-indexer App Profile
and an `autoSearch` flag are included in the data for transparency.

## Quick start (Docker)

```yaml
services:
  prowlarr-indexer-report:
    image: ghcr.io/tikibozo/prowlarr-indexer-report:latest
    container_name: prowlarr-indexer-report
    environment:
      - PROWLARR_URL=http://prowlarr:9696
      - PROWLARR_API_KEY=<your-prowlarr-api-key>
      - WINDOW_DAYS=90
      - REFRESH_INTERVAL_MINUTES=15
    ports:
      - 8787:8787
    restart: unless-stopped
```

Open `http://<host>:8787`. The API key is in Prowlarr under
**Settings → General → API Key**.

## Configuration

| Env var | Default | Description |
|---|---|---|
| `PROWLARR_API_KEY` | *(required)* | Prowlarr API key. |
| `PROWLARR_URL` | `http://localhost:9696` | Base URL of the Prowlarr instance (server-to-Prowlarr). |
| `PROWLARR_PUBLIC_URL` | *(unset)* | Browser-facing Prowlarr URL. When set, the report deep-links to Prowlarr (header + flagged indexers). Leave unset if `PROWLARR_URL` is a Docker-internal host the browser can't reach. |
| `WINDOW_DAYS` | `90` | Recent window for trend columns + removal heuristic. |
| `REFRESH_INTERVAL_MINUTES` | `15` | How often the service re-queries Prowlarr. |
| `HOST` / `PORT` | `0.0.0.0` / `8787` | Bind address/port for the web UI. |

## Endpoints

| Path | Purpose |
|---|---|
| `GET /` | Live report UI. |
| `GET /api/data` | Cached report as JSON. `503` until the first fetch completes. |
| `POST /api/refresh` | Force an out-of-band refresh (the UI's "Refresh now" button). |
| `GET /healthz` | Liveness; reports last success/error without failing on a transient Prowlarr outage. |

## Security

The web UI is **unauthenticated by design** — the report reveals which (often
private) trackers you use, so deploy it on a trusted network or behind your own
reverse proxy / SSO. The only secret is `PROWLARR_API_KEY`, read from the
environment and never logged. See [SECURITY.md](SECURITY.md).

## Development

```bash
uv sync --all-extras
uv run ruff check .
uv run pytest -q

# Run locally against a real Prowlarr:
PROWLARR_URL=http://localhost:9696 PROWLARR_API_KEY=... uv run uvicorn app.main:app --reload --port 8787

# Preview the UI without a Prowlarr (serves the front-end + fictional demo data):
python dev/mock_server.py            # then open http://localhost:8787
```

`dev/mock_server.py` is stdlib-only (no Prowlarr, no API key, no deps) and is
what generates the screenshot above; it's handy for UI work.

The analysis lives in `app/prowlarr.py`: `ProwlarrClient` does the async HTTP,
and `compute_report` is a pure function over the fetched payloads (which is what
the tests exercise). The UI is static (`app/static/`, Chart.js vendored).

## Releasing

Commits follow [Conventional Commits](https://www.conventionalcommits.org/).
release-please opens a release PR; merging it tags the version and the Release
workflow builds a Trivy-gated multi-arch image to
`ghcr.io/tikibozo/prowlarr-indexer-report`.

## License

[MIT](LICENSE)
