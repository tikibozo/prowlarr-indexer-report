---
name: Prowlarr Indexer Usefulness Report
description: A dark operator's instrument whose disable/watch verdict leads, and whose evidence follows.
colors:
  navy-base: "#0f1420"
  slate-panel: "#1a2133"
  slate-raised: "#202a40"
  hairline: "#2a3450"
  ink: "#e6ebf5"
  muted: "#8a96ad"
  usenet-blue: "#4ea1ff"
  torrent-amber: "#ffb454"
  remove-red: "#ff5c6c"
  watch-yellow: "#ffcf5c"
  manual-teal: "#5cd0d0"
  ok-green: "#7ce38b"
  app-violet: "#c08cff"
  app-pink: "#ff8fab"
typography:
  display:
    fontFamily: "-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif"
    fontSize: "22px"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "-0.01em"
  headline:
    fontFamily: "-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif"
    fontSize: "17px"
    fontWeight: 700
    lineHeight: 1.3
    letterSpacing: "normal"
  title:
    fontFamily: "-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif"
    fontSize: "15px"
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: "normal"
  metric:
    fontFamily: "-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif"
    fontSize: "24px"
    fontWeight: 700
    lineHeight: 1.1
    letterSpacing: "normal"
  body:
    fontFamily: "-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: "normal"
  label:
    fontFamily: "-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif"
    fontSize: "12px"
    fontWeight: 400
    lineHeight: 1.4
    letterSpacing: "0.04em"
rounded:
  xs: "4px"
  sm: "7px"
  md: "10px"
  lg: "12px"
  pill: "20px"
spacing:
  xs: "6px"
  sm: "8px"
  md: "14px"
  lg: "18px"
  gutter: "28px"
components:
  button-primary:
    backgroundColor: "{colors.slate-panel}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "5px 12px"
  button-primary-hover:
    backgroundColor: "{colors.slate-panel}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "5px 12px"
  card:
    backgroundColor: "{colors.slate-panel}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: "12px 16px"
  card-verdict:
    backgroundColor: "{colors.slate-raised}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: "12px 16px"
  chip:
    backgroundColor: "{colors.slate-panel}"
    textColor: "{colors.muted}"
    rounded: "{rounded.pill}"
    padding: "3px 12px"
  chip-active:
    backgroundColor: "{colors.slate-raised}"
    textColor: "{colors.ink}"
    rounded: "{rounded.pill}"
    padding: "3px 12px"
  pill-remove:
    backgroundColor: "{colors.remove-red}"
    textColor: "{colors.navy-base}"
    rounded: "{rounded.pill}"
    padding: "1px 8px"
  pill-watch:
    backgroundColor: "{colors.watch-yellow}"
    textColor: "{colors.navy-base}"
    rounded: "{rounded.pill}"
    padding: "1px 8px"
---

# Design System: Prowlarr Indexer Usefulness Report

## 1. Overview

**Creative North Star: "The Operator's Verdict"**

This is an instrument, not a dashboard. A self-hoster opens it with a single question — *which of my indexers earn their keep, and which can I safely disable?* — and the interface answers before it explains. The verdict (a remove/watch/manual ruling on every indexer) is the lede: colored, named, and reachable in the first screen. The five charts that justify the ruling are demoted to a collapsible **Analysis** section below the decision. The voice is a knowledgeable peer who has already done the analysis and states the call plainly, then shows the work — every flag carries its reason and its data window.

The surface is a dark, dense, single-page console: a deep-navy base, raised-slate panels separated by 1px hairlines and tonal lightness rather than shadow, a strict one-hue-per-meaning color system, and the system font at working sizes. No imagery, no gradients, no ornament — color and weight carry every distinction. Density is embraced (a 13-column table, six summary tiles, five charts) but spined: hierarchy makes the eye land on the verdict first and drill down second.

It explicitly rejects three things. It is **not a generic admin-panel / Bootstrap-default dashboard** — evenly gray cards in a rigid grid with no point of view. It is **not consumer-SaaS marketing gloss** — purple gradients, oversized hero numbers without context, playful illustration. And it is **not a Grafana-style raw-metric wall** — every panel equal weight, the user left to find the signal. Here the signal is surfaced for them.

**Key Characteristics:**
- Verdict-first hierarchy: the ruling precedes the evidence.
- One accent per meaning; semantics never rest on hue alone.
- Flat by default — depth is tonal layering + hairlines, never decorative shadow.
- Honest about freshness: live status, staleness, and coverage gaps are first-class UI.
- System-font, dark, dense — a tool that disappears into the task.

## 2. Colors

A near-monochrome navy field carrying a small, disciplined set of semantic accents — each hue means exactly one thing.

### Primary
- **Operator Navy** (`#0f1420`): the page base. The deep, low-glare field a console sits in; everything else is layered on top of it.
- **Signal Blue** (`#4ea1ff`): the usenet protocol and the primary timeline series. Doubles as the focus-ring color — the one interactive "you are here" accent.

### Secondary (semantic verdict accents)
- **Remove Red** (`#ff5c6c`): the disable verdict — flag pill, tinted table row, kill-list item, remove count.
- **Watch Yellow** (`#ffcf5c`): the high-cost warning — watch flag and stale-status dot.
- **Manual Teal** (`#5cd0d0`): the neutral interactive-only ruling; deliberately cool and calm, never alarming.
- **OK Green** (`#7ce38b`): healthy / live status dot and the 30-day trend series.
- **Torrent Amber** (`#ffb454`): the torrent protocol counterpart to Signal Blue.

### Tertiary (categorical only)
- **App Violet** (`#c08cff`) and **App Pink** (`#ff8fab`): used *only* in the per-app stacked chart's categorical series, never as semantic UI. They exist to separate adjacent app series, paired with texture so they survive grayscale.

### Neutral
- **Raised Slate** (`#1a2133`): cards, panels, table, buttons — the standard raised surface.
- **Console Slate** (`#202a40`): the second raised layer — verdict cards and the pressed/active chip, one step brighter to pull the eye.
- **Hairline** (`#2a3450`): all borders, grid lines, dividers. Separation is by line and tone, not shadow.
- **Ink** (`#e6ebf5`): primary text.
- **Muted** (`#8a96ad`): secondary text, labels, axis ticks. Verified ~5.4:1 on Raised Slate and ~6.2:1 on Operator Navy — both pass WCAG AA; do not lighten it further.

### Named Rules
**The One-Accent-Per-Meaning Rule.** Each semantic hue maps to exactly one meaning — remove=red, watch=yellow, manual=teal, ok=green, usenet=blue, torrent=amber. A semantic hue is never reused decoratively or for a second meaning. If a new state needs a color, it earns a new token; it does not borrow an existing one.

**The Color-Plus-Label Rule.** Status is never carried by hue alone. Every flag and protocol also carries a text label (pills read "remove" / "watch" / "usenet"), the scatter encodes flags as point *shapes* (▲ remove / ■ watch / ● ok), and chart bars carry *patterns* (solid usenet / hatched torrent). The interface must stay legible in grayscale and to color-blind users — this is a product requirement, not a nicety.

## 3. Typography

**Display / Body / Label Font:** the native system stack — `-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif`. One family throughout, set in both CSS and `Chart.defaults.font.family`. No web fonts ship.

**Character:** invisible-by-design. A console's type should read as part of the OS, not as a brand statement. Personality comes from weight contrast and the color system, not from a typeface.

### Hierarchy
- **Display** (700, 22px, slight `-0.01em` tracking): the single page H1.
- **Headline** (700, 17px): "The verdict" — the one heading sized to out-rank everything, because the verdict leads.
- **Title** (600, 15px): panel, section, and chart headings.
- **Metric** (700, 24px): the big summary-card numbers. On verdict cards this number is tinted to its semantic hue; on inventory cards it stays Ink.
- **Body** (400, 13–14px): table cells, captions, reasons. Data and compact UI run dense; prose (chart captions, the empty-state line) stays comfortably readable.
- **Label** (400, 12px, `0.04em`, uppercase): summary-card labels only. The one place tracked-uppercase is allowed; it is not sprinkled as section eyebrows.

### Named Rules
**The System-Font Rule.** No web fonts, ever. Hierarchy is built from weight (700 vs 400) and size, not from family pairing. A second typeface would read as gloss on an instrument.

## 4. Elevation

Flat. Surfaces never cast a resting shadow; depth is built from three things — a tonal stack of surface lightness (Operator Navy → Raised Slate → Console Slate), a 1px Hairline border on every panel, and proximity. The page reads as layered paper under even light, not as floating cards.

Shadow exists in exactly three places, and only ever as a *state* signal, never as decoration:

### Shadow Vocabulary
- **Status glow** (`box-shadow: 0 0 0 3px color-mix(in srgb, <status hue> 22%, transparent)`): the soft ring around the live/stale/error status dot — a halo that reads as "transmitting".
- **Focus ring** (`outline: 2px solid #4ea1ff; outline-offset: 2px`): keyboard focus on every interactive element.
- **Active-filter ring** (`box-shadow: inset 0 0 0 1px <semantic hue>`): the selected verdict card, ringed in its own meaning's color.

### Named Rules
**The Flat-By-Default Rule.** Surfaces are flat at rest. If you are about to add a drop shadow to lift a card, stop — raise its surface one tonal step (Raised Slate → Console Slate) or tighten its border instead. Shadow is reserved for live state, focus, and active selection. If the verdict panel ever needs to "pop", the answer is hierarchy and color, never a shadow.

## 5. Components

### Buttons
- **Shape:** gently rounded (7px / `{rounded.sm}`).
- **Primary:** Raised Slate fill, Ink text, 1px Hairline border, compact `5px 12px` padding. The default and only button weight — "Refresh now", "Copy disable list".
- **Hover / Focus:** border brightens to Muted on hover (150ms ease); focus shows the Signal-Blue ring. Disabled drops to 50% opacity, cursor default.
- **Link button** (`.btn-link`): an anchor styled identically to a button, for "Open Prowlarr ↗" — same shape, fill, and hover. Only rendered when a browser-facing Prowlarr URL is configured.

### Chips (table filters)
- **Style:** pill-shaped (20px), Raised Slate fill, Muted text, Hairline border. Carry a live count (e.g. "Remove 3").
- **State:** the active filter switches to Console Slate fill + Ink text + Muted border, mirrored by `aria-pressed`. Selection is also reflected on the corresponding verdict card's active ring.

### Cards / Containers
- **Corner style:** 10px (`{rounded.md}`); the verdict panel is one step softer at 12px.
- **Background:** inventory cards on Raised Slate; verdict cards on Console Slate (one tonal step up) to mark them as the actionable set.
- **Shadow strategy:** none at rest — see Elevation. Verdict cards gain the inset semantic ring only when active.
- **Border:** 1px Hairline always.
- **Distinctive behavior:** verdict cards are interactive — `role="button"`, keyboard-operable, their metric tinted to the verdict hue. When their count is zero they dim to ~55% and drop interactivity. Inventory and verdict cards are separated by a thin vertical divider, differentiating role by color and interactivity, **not by size**.

### Data Table
- **Style:** full-width, 13px, Hairline row dividers, right-aligned numerics, left-aligned first column and reason.
- **Sortable headers:** each header is a real `<button>` inside the `<th>`, keyboard-operable, with `aria-sort` reflecting state and a ▾/▴ arrow on the active key. A `title` tooltip explains every abbreviated header (Prio, Win, Resp ms…).
- **Row semantics:** flagged rows tint at low alpha (remove/watch/manual); disabled rows drop to 50% opacity. Flag, protocol, and disabled state render as **pills** (text + color), never color alone.
- **Sticky header** on a `--z-sticky` layer; the wrap scrolls within a Hairline-bordered, 10px-radius frame.

### Signature Component — The Verdict Panel
The lede of the page and its reason for existing. A 12px-radius panel directly under the summary cards, titled "The verdict — N safe to disable, N to watch", with a "Copy disable list" action (and "Open Prowlarr ↗" when configured). Inside, two columns (remove / watch) of **kill-list items**: each a small tinted card with the indexer name, a right-aligned micro-stat line (grabs · queries · last grab), and the verdict reason beneath. When a public Prowlarr URL is set, each name links out to Prowlarr's indexer list (↗) — Prowlarr edits indexers in a modal with no addressable per-indexer route, so the link opens the list rather than a specific indexer, and its tooltip says so. When nothing is flagged, it resolves to a reassuring, teaching empty state in OK Green: *"Nothing to prune. Every enabled auto-search indexer is earning its keep."*

### Status & Freshness
A right-aligned header cluster: a recoloring dot (OK Green / Watch Yellow / Remove Red) with a glow ring, a plain-language age line ("data 3m ago · window 60d · server refresh 30m"), and coverage span. A full-width Remove-Red-tinted banner (`role="alert"`) appears only on truncation or fetch failure. State *transitions* (live → stale → error) are announced to screen readers via a dedicated visually-hidden `aria-live` region — the ticking age is not, to avoid spam.

### Loading & Motion
First load shows **skeleton** tiles (cards + verdict + table) with a shimmer, not a spinner. Transitions are 150ms on borders/colors only; a smooth-scroll carries a verdict-card click down to the table. Chart.js animations are disabled — data swaps in place, and unchanged server snapshots skip re-render entirely so polling never flashes the charts. Every motion (shimmer, smooth-scroll) has a `prefers-reduced-motion` off-switch.

## 6. Do's and Don'ts

### Do:
- **Do** lead with the verdict. The remove/watch ruling is the most legible thing on the page and appears before any chart. **The Verdict-Leads Rule** is the product.
- **Do** pair every semantic color with a text label or shape — pills, point shapes, bar patterns. Assume grayscale and color-blindness.
- **Do** build depth from tonal layers (Operator Navy → Raised Slate → Console Slate) and 1px Hairlines. Raise a surface a step before you reach for a border change; never reach for a shadow.
- **Do** keep Muted (`#8a96ad`) as the floor for secondary text — it passes AA on both dark surfaces. Verify any new text color against its actual background.
- **Do** state the reason and data window on every flag. Confidence comes from transparency.
- **Do** keep one system font; build hierarchy from weight and size.

### Don't:
- **Don't** ship a **generic admin-panel / Bootstrap-default dashboard** — evenly gray cards in a rigid grid with no point of view. This tool has opinions; the UI must too.
- **Don't** add **consumer-SaaS marketing gloss** — purple gradients, oversized hero numbers without context, playful illustration. This is an operator's instrument.
- **Don't** build a **Grafana-style raw-metric wall** — every panel equal weight, the user left to hunt for the signal. Surface the signal (what to disable) for them.
- **Don't** use a drop shadow to lift a surface, or any decorative shadow. Shadow is reserved for live state, focus, and active selection (**The Flat-By-Default Rule**).
- **Don't** carry meaning in hue alone, reuse a semantic accent for a second meaning, or introduce a gradient.
- **Don't** put a tracked-uppercase eyebrow above every section, or a `border-left` color stripe on cards/items. Uppercase is for summary-card labels only.
- **Don't** lighten Muted "for elegance" — light gray body text on tinted navy is the readability failure this system is built to avoid.
