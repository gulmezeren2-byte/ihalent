"""MCP server: expose ihalent's analytics to an agent runtime.

Structure to note: every tool's real work lives in a plain function that
returns a dict and knows nothing about MCP. The MCP layer at the bottom is a
thin wrapper registered only when the `mcp` extra is installed. That split
keeps the logic unit-testable without an agent runtime and keeps `mcp` out of
the core's dependency set.

The dataset is a JSONL path, taken from the IHALENT_AWARDS environment variable
(or passed per call). Point it at the awards file you produced with
`ihalent ingest`.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ihalent.analytics import by_group, concentration, firm_profile, overview, slice_awards
from ihalent.ingest import ingest_bundle
from ihalent.parse import NotAResultNotice, parse_result_notice
from ihalent.store import load_awards

ENV_AWARDS = "IHALENT_AWARDS"


def _resolve(path: str | None) -> Path:
    p = path or os.environ.get(ENV_AWARDS)
    if not p:
        raise ValueError(
            f"No awards dataset given. Pass awards_path, or set {ENV_AWARDS} to a "
            f"JSONL file produced by `ihalent ingest`."
        )
    return Path(p)


# -- tool logic (MCP-independent, unit-tested) --------------------------------


def tool_overview(awards_path: str | None = None) -> dict[str, Any]:
    """Summary of a dataset: awarded value, discount, competition, and data gaps."""
    return overview(load_awards(_resolve(awards_path))).to_dict()


def tool_firm(name: str, awards_path: str | None = None) -> dict[str, Any]:
    """Profile one company across the dataset: wins, total value, discount, where it wins.
    Spelling variants of the same company fold together."""
    profile = firm_profile(load_awards(_resolve(awards_path)), name)
    if profile is None:
        return {"found": False, "query": name}
    return {"found": True, **profile.to_dict()}


def tool_discounts(by: str = "authority", awards_path: str | None = None) -> dict[str, Any]:
    """Discount (kırım) distribution grouped by 'authority', 'province' or 'tender_type'."""
    groups = by_group(load_awards(_resolve(awards_path)), by)
    return {"group_by": by, "groups": [g.to_dict() for g in groups]}


def tool_concentration(
    authority: str | None = None,
    province: str | None = None,
    top: int = 5,
    awards_path: str | None = None,
) -> dict[str, Any]:
    """Winner concentration (HHI) over the dataset, or a slice of it by authority
    or province. Where single-bid share measures competition within a tender,
    this measures it across tenders: are the same few firms winning everything?
    Returns the HHI (0..1 over win counts), the leading firms, and the coverage."""
    awards = load_awards(_resolve(awards_path))
    subset, label = slice_awards(awards, authority=authority, province=province)
    return concentration(subset, label=label, top=top).to_dict()


def tool_parse_notice(markdown: str) -> dict[str, Any]:
    """Parse a single result-notice (Sonuç İlanı) markdown into a structured award."""
    try:
        return parse_result_notice(markdown).to_dict()
    except NotAResultNotice as exc:
        return {"error": str(exc)}


def tool_ingest_bundle(bundle: Any, awards_path: str | None = None) -> dict[str, Any]:
    """Structure collected ihale-mcp/EKAP output into awards and append them to the
    dataset file. Returns how many awards with result notices were written."""
    from ihalent.store import dump_awards

    awards = ingest_bundle(bundle)
    if not awards:
        return {"written": 0, "note": "no result notices found in the bundle"}
    path = _resolve(awards_path)
    existing = load_awards(path) if path.is_file() else []
    merged = {a.ikn: a for a in existing}
    merged.update({a.ikn: a for a in awards})
    written = dump_awards(list(merged.values()), path)
    return {"written": written, "new_in_bundle": len(awards), "dataset": str(path)}


TOOLS = [
    tool_overview,
    tool_firm,
    tool_discounts,
    tool_concentration,
    tool_parse_notice,
    tool_ingest_bundle,
]


# -- MCP wrapper (needs the `mcp` extra) --------------------------------------


def build_server() -> Any:
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise SystemExit(
            "The MCP server needs the optional dependency: pip install 'ihalent[mcp]'"
        ) from exc

    server = FastMCP("ihalent")
    for fn in TOOLS:
        server.tool()(fn)
    return server


def main() -> None:  # pragma: no cover - transport entry point
    build_server().run()


if __name__ == "__main__":  # pragma: no cover
    main()
