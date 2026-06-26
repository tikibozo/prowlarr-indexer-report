# Product

## Register

product

## Users

Self-hosters running the *arr media stack (Prowlarr + Sonarr/Radarr/Lidarr).
They're technical, comfortable in a terminal and a Docker compose file, and they
run this as a small containerized web service alongside the rest of their stack.
Their context when they open it: "which of my indexers actually earn their keep,
and which can I safely disable?" They want to scan, decide, and leave — this is a
periodic operational tool, not something they sit in all day. A secondary
audience is anyone evaluating the project from its public repo, where the README
screenshot is the first impression that decides whether they deploy it.

## Product Purpose

Turn Prowlarr's thin built-in indexer stats into a report you can act on. It
ranks every indexer by grabs, shows recent trend, exposes query cost / failure /
latency, breaks grabs down by the consuming app, and flags indexers that are
safe to disable. Success is a user looking at the page and confidently pruning or
keeping an indexer in under a minute — the flags and ranking do the reasoning so
they don't have to. All Prowlarr calls are read-only; the tool advises, it never
acts on the user's behalf.

## Brand Personality

Sharp, opinionated, trustworthy. Three words: **decisive, technical, honest**.
The voice is a knowledgeable peer who has already done the analysis and tells you
the verdict plainly ("the long tail at the bottom does little for you") rather
than dumping raw numbers and leaving you to interpret. It earns trust by showing
its work — every flag states its reason, coverage windows are explicit, and it
warns when data might be incomplete rather than silently dropping it.

## Anti-references

- **Generic admin-panel / Bootstrap-default dashboards** — evenly gray cards in a
  rigid grid with no point of view. This tool has opinions; the UI should too.
- **Consumer SaaS marketing gloss** — purple gradients, oversized hero numbers
  with no context, playful illustration. This is an operator's instrument.
- **Grafana-style raw-metric walls** — every panel equal weight, no hierarchy,
  the user left to find the signal. The whole point here is that the signal
  (what to disable) is surfaced for them.

## Design Principles

1. **The verdict leads.** Disable/watch/keep flags and ranking are the product;
   they should be the most legible thing on the page, not buried in a wide table.
2. **Show your work.** Every recommendation states its reason and its data window.
   Confidence comes from transparency, not from hiding the inputs.
3. **Dense, but with a spine.** It's a data-heavy operator tool, so don't fight
   the density — give it a clear visual hierarchy so the eye lands on what matters
   first and drills down second.
4. **Distinctive, not decorative.** A real visual identity so it doesn't read as a
   generic panel — but every distinctive choice must still serve scanning and
   decision-making, never ornament for its own sake.
5. **Honest about freshness.** Live-polling state, staleness, and coverage gaps
   are first-class UI, not afterthoughts — the data's trustworthiness is part of
   the product.

## Accessibility & Inclusion

- Dark-first interface; maintain WCAG AA contrast (4.5:1 text, 3:1 large/UI) on
  the dark base — the current muted gray on navy is borderline and should be
  verified.
- Status and flags must not rely on color alone — the disable/watch/keep and
  usenet/torrent distinctions need a text label or shape in addition to hue, for
  color-blind users (red/green and blue/amber are the at-risk pairs here).
- Respect `prefers-reduced-motion` for any chart-load or live-update animation.
- Charts should remain interpretable when reduced to grayscale.
