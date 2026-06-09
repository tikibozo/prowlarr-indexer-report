# Security Policy

## Reporting a vulnerability

Open a [GitHub security advisory](https://github.com/tikibozo/prowlarr-indexer-report/security/advisories/new)
or a private issue. Please do not disclose security issues publicly until a fix
is available.

## Scope & handling

This service is read-only against the Prowlarr API and holds a single secret —
the Prowlarr API key (`PROWLARR_API_KEY`), supplied via the environment. It is
never logged and should be provided via a secret manager or env file, never
committed. The published container image is scanned with Trivy (HIGH/CRITICAL,
fixable) before every publish and re-scanned weekly.

The web UI is unauthenticated by design — deploy it on a trusted network or
behind your own reverse proxy / SSO if exposure is a concern.
