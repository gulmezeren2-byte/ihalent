# Changelog

## 0.1.0 — 2026-07-17

First public release.

- Parse EKAP result notices (Sonuç İlanı) into structured `Award` records: İKN, estimate,
  contract price, winner (with joint-venture members), bid counts, dates — deterministically,
  with missing fields left `None` rather than guessed.
- Analytics: firm profiles (folded across spelling variants), discount (kırım) distributions
  grouped by authority / province / tender type, and competition stats including single-bid
  share.
- The coverage discipline: every statistic reports how many records it used and how many it
  dropped for missing data; discounts are never computed from a missing estimate.
- `ingest` from ihale-mcp / EKAP output (pure function, no network), plus `overview`, `firm`,
  `discounts` and `parse` commands, each with a `--json` form.
- Worked example built from four real December-2025 awards across four authority types,
  including a negative-discount emergency-procurement case and the code that structures them.
- 44 tests over the exact JSON shapes EKAP and ihale-mcp emit.
