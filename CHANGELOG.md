# Changelog

## Unreleased

- **Read the Kamu İhale Bülteni (`ihalent fetch-bulletin`, `ihalent ingest-bulletin`).**
  Since September 2026 EKAP's search API asks for human verification, so collecting
  notices with ihale-mcp from your own machine fails with HTTP 428 (issue #1). ihalent
  does not try to get past that. It now reads the daily bulletin KİK publishes every
  result notice in, by law, on a public page: `fetch-bulletin` downloads the files (one
  per working day and tender type, at least two seconds apart, never twice, and it stops
  at the first verification screen or refusal), and `ingest-bulletin` reads them. The
  notice form's two columns don't line up row by row, so labels and values are paired
  cell by cell; every file is checked against its own table of contents, and a notice
  that doesn't add up is rejected, not guessed. A notice that states it has no estimate
  ("- TRY", or a sentence saying so) is read with the estimate left empty. A contract
  priced in euros or dollars is not counted as lira: its lira price is left empty, with
  no exchange rate guessed (nine goods notices of 12–13 November 2026 do this), and an
  estimate printed in lira beside its foreign original is read in lira. An İKN with a
  numbered suffix (`2026/1007522-4`) is kept as printed. Verified on 883 of 883 notices:
  the works and goods bulletins of 12 and 13 November 2026 and the service and
  consultancy bulletins of the 13th, all fetched with `fetch-bulletin` (the two goods
  days in one `--since` run). Needs the new `bulletin` extra (pdfplumber).
- **New field `lots_unverified`, and no discount for it.** A tender awarded in parts gets
  one notice per lot, published on different days, each with the tender-wide estimate.
  Merged, its contracts are summed, but its discount is now `null`: nothing says when the
  last lot has been printed. Records written before this field load as before.
- **Fixed: a firm that won one lot was credited the whole tender.** A merged record kept
  only the summed contract, so `firm` gave every lot winner the full sum and
  `concentration` gave all of it to the first lot's winner (on the works bulletins of
  12–13 November 2026, one firm showed 5.3 million TL where its two lots came to
  1.6 million). Records now keep `lots` — who won each lot, for how much — and both
  views credit a firm only its own lots; `concentration` counts each lot as its own
  award. Records written before this still load, but without `lots` they credit as
  before: run `ingest` / `ingest-bulletin` again to get the per-lot credit.
- **A tender in lots is no longer called "missing data".** It has no discount (its other
  lots may still come) and no tender-wide bid count (bid counts are per lot); the
  summaries now say "awarded in lots", and the overview no longer counts it as an
  award without a bid count. In `flags`, such a tender's row shows "N lots" instead of
  the first lot's winner beside the whole tender's sum.
- **Fixed: `result_date` is the contract date, as the schema always said.** The markdown
  parser for ihale-mcp notices took the first date in the notice, which is the tender
  date. It now reads the date in the contract section (`4- Sözleşmenin`), and leaves
  `result_date` empty when that section prints none — as six of the shipped example
  notices do, so the example dataset changed accordingly. Bulletin records read the
  contract date too.

## 0.3.2 — 2026-07-30

- **Fixed: the MCP server would not start with version 2 of the MCP SDK.** The SDK
  renamed its high-level server class between majors — `mcp.server.fastmcp.FastMCP`
  in 1.x, `mcp.server.MCPServer` in 2.x — and removed the old module outright, so a
  fresh `pip install 'ihalent[mcp]'` resolved SDK 2.0.0 and the server died at import.
  Both spellings are now accepted; they are drop-in for what is used of them, so
  nobody is pinned to one SDK generation.
- **And the error no longer sends you in a circle.** The old handler treated every
  import failure as a missing optional dependency and said to install the extra —
  which, once the SDK moved, was advice to repeat the step you had already done. A
  package that isn't installed and an SDK that moved are different problems, and are
  now reported as such.


## 0.3.1 — 2026-07-29

- **Fixed a crash when output is piped on Windows.** A piped stdout gets the legacy
  code page rather than UTF-8, and every report here is full of Turkish — firm names
  like `ÖZKAN İNŞAAT LTD. ŞTİ.`, labels like `kırım` — which raised
  `UnicodeEncodeError` and took the command down. So `ihalent overview … | tee`, and
  any CI step capturing the log, failed on ordinary data. Output streams are now asked
  for UTF-8, and the guard never fails if a stream won't take it.

## 0.3.0 — 2026-07-17

- **Procurement red flags (`ihalent flags`)**: per-award risk signals used in transparency
  work — a single valid bid, a contract that landed at or above the public estimate (no
  downward price pressure), a missing estimate (so it can't be audited), or a tender many
  firms took documents for but almost none bid on. None is proof of anything; each is a
  reason to open the file. Reports per-flag counts and the most-flagged awards (most flags,
  then most money, first), with the coverage it stands on. Exposed as a CLI command, a
  `flags` MCP tool, and `ihalent.analytics.risk_flags`.

## 0.2.0 — 2026-07-17

- **Winner concentration (`ihalent concentration`)**: the Herfindahl-Hirschman Index over a
  dataset, or a slice of it by `--authority` / `--province`, with the leading firms and their
  win shares. Where single-bid share measures competition *within* a tender, this measures it
  *across* tenders — are the same few firms winning everything a buyer puts out? Spelling
  variants fold together, each award is attributed to its lead winner, and the coverage
  travels with the number (high concentration in a thin slice is arithmetic, not evidence).
  Exposed three ways: the CLI command, a `concentration` MCP tool, and
  `ihalent.analytics.concentration`.
- `slice_awards` helper (authority/province substring filter) shared by the CLI and MCP
  server, so a "concentration within this authority" query means the same thing in both.

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
- Optional MCP server (`pip install 'ihalent[mcp]'`, `ihalent-mcp`) exposing the analytics as
  agent tools over a dataset from `IHALENT_AWARDS`.
- Worked example built from four real December-2025 awards across four authority types,
  including a negative-discount emergency-procurement case and the code that structures them.
- 44 tests over the exact JSON shapes EKAP and ihale-mcp emit.
