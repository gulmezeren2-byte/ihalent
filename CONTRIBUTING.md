# Contributing

Thanks for considering it. ihalent stays useful only if it stays honest about what it does
and does not know, so a few rules protect that.

## Ground rules

- **The core is a pure function of its input.** No network calls, no signing keys, no live
  scraping in `parse`, `analytics`, `ingest` or `store`. Collection is ihale-mcp's job.
- **Never invent a number.** A missing field is `None`, not `0` or `""`. A statistic reports
  its coverage. If a change would let a mean hide how many records lacked the value, it's the
  wrong change.
- **Parsing changes ship with a real notice.** The tests are built on the exact markdown EKAP
  serves. If you handle a new notice variant, add the real (trimmed) notice that motivated it
  to `tests/` so the parser is pinned to reality, not to a tidy invention.
- **Company-name folding errs toward splitting, not merging.** Merging two real firms into one
  row corrupts the analysis silently; showing two rows for one firm is visible and fixable.
  New normalization rules need a test that they don't over-merge.

## Mechanics

```
uv sync --dev
uv run pytest
uv run ruff check src tests
uv run mypy src
```

All three must be clean; CI runs them on Linux and Windows. Keep PRs scoped to one change,
and if you touch the parser or the example, re-run `python examples/build_sample.py` in the
same PR so the committed sample matches the code.
