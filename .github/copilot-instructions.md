# Copilot instructions — ihalent

Turkish public-tender (EKAP) award intelligence: a pure-Python library + Typer CLI (plus an optional MCP server) that parses result notices (*Sonuç İlanı*) into `Award` records and computes firm histories, discount (kırım) distributions, and competition metrics — every number traceable to its source notice.

## Build, test, lint

Dependencies and tools are managed with `uv` (`uv.lock`); Python 3.10+ (CI matrix: 3.10 and 3.14 on Linux + Windows). All three must be clean before a PR:

```bash
uv sync --dev
uv run pytest
uv run ruff check src tests     # line-length 100; rules E,F,I,UP,B,SIM,RET,C4
uv run mypy src                 # disallow_untyped_defs, no_implicit_optional
```

If you touch the parser or `examples/`, rebuild the committed sample and confirm it round-trips (CI enforces this exact check):

```bash
uv run python examples/build_sample.py
uv run ihalent overview examples/sample-awards.jsonl --json | grep -q '"min": -2.96'
```

Entry points (`pyproject.toml` scripts): `ihalent` (CLI) and `ihalent-mcp` (MCP server — needs the extra `pip install 'ihalent[mcp]'`, pointed at data via the `IHALENT_AWARDS` env var).

## Architecture

All code lives under `src/ihalent/`. Pipeline: notice markdown -> `parse.py` (regex only, no ML/heuristics) -> `Award` dataclass (`model.py`) -> JSONL via `store.py` -> `analytics.py` -> `render.py` / `cli.py` / `mcp_server.py`. `ingest.py` turns an ihale-mcp/EKAP bundle into awards (merging per-lot *kısmi teklif* notices); `normalize.py` folds company-name spellings. The core is a **pure function of its input** — no network, no scraping, no keys; collection is delegated to the external `saidsurucu/ihale-mcp`. JSONL is the interchange boundary (one award per line, deduped by İKN, last line wins). In `mcp_server.py` each tool is a plain dict-returning function that knows nothing about MCP; the `FastMCP` wrapper (optional `mcp` extra) is imported lazily so the core stays dependency-light.

## Conventions

- **Never invent a number.** A missing field is `None`, never `0` or `""`; `discount_pct` is `None` (not `0`) when the estimate is absent or zero. Every statistic carries a `Coverage` (considered/used/excluded) and the renderer always prints it.
- **Parsing changes ship with a real notice.** Add the actual (trimmed) EKAP markdown that motivated the change to `tests/` — fixtures in `conftest.py` embed real notice rows verbatim (hence `E501` is ignored there), so green tests mean the real template still parses.
- **Company-name folding errs toward splitting, not merging** (`normalize.py`); new normalization rules need a test proving they don't over-merge, and `firm` reports `distinct_spellings`.
- `--json` output is ASCII (`ensure_ascii=True`) and field-stable for agents/pipelines; human output uses `rich`. Turkish text needs explicit İ/ı folding, not `str.lower()`; money is `.`-thousands / `,`-decimal.
- Typed package (`py.typed` shipped); CLI exit codes are meaningful (`2` = bad input/usage, `1` = no match/empty).
