# Security

## Model

ihalent is a local, offline tool: the parse + analytics core makes no network calls
(live collection is [ihale-mcp](https://github.com/saidsurucu/ihale-mcp)'s job, behind a
separate extra), and it has no code path that writes to your data. The attack surface that
remains:

- **Datasets are JSON/JSONL and result-notice markdown that you load.** ihalent reads the
  awards file you point it at and parses notice text; a hostile file is a parsing-robustness
  concern, not a code-execution one — dataset contents are never `eval`'d. Keep dependencies
  current.
- **The MCP server reads the path in `IHALENT_AWARDS` (or the per-call argument),** and only
  reads it. Point it at data you control.

## Reporting

Report vulnerabilities through GitHub's private security advisories on this repository
(Security → Report a vulnerability). I'll acknowledge within a few days.
