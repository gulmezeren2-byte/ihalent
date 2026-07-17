"""Regenerate docs/demo.svg from the sample dataset.

The README screenshot is not a mock-up: it is `ihalent overview`,
`ihalent concentration` and `ihalent flags` rendered over
examples/sample-awards.jsonl. Re-run after changing the sample or the renderers
so the README never lies about what the tool prints.

    uv run python examples/make_demo_svg.py

Why SVG and not a PNG screenshot: ihalent already depends on rich, whose
Console(record=True) exports a terminal-accurate SVG with no new dependency,
and — unlike pasting a Windows console screenshot — it keeps Turkish
characters (kırım, İSKİ, Kağıthane) as real text. We strip rich's CDN
@font-face rule afterwards so GitHub (which blocks external fetches in SVG)
renders it with the system monospace instead of empty boxes.
"""

from __future__ import annotations

import re
from pathlib import Path

from rich.console import Console

from ihalent.analytics import concentration, overview, risk_flags
from ihalent.render import render_concentration, render_overview, render_risk
from ihalent.store import load_awards

ROOT = Path(__file__).parent.parent


def main() -> None:
    awards = load_awards(ROOT / "examples" / "sample-awards.jsonl")
    console = Console(record=True, width=94)

    # overview → concentration → red flags: the arc from "what is this dataset"
    # to "where should a reader look."
    render_overview(overview(awards), console)
    render_concentration(concentration(awards, top=3), console)
    render_risk(risk_flags(awards), console)

    svg = console.export_svg(title="ihalent")
    # Drop the CDN font-face so the SVG is self-contained on GitHub.
    svg = re.sub(r"@font-face\s*\{[^}]*?\}", "", svg, flags=re.DOTALL)
    out = ROOT / "docs" / "demo.svg"
    out.parent.mkdir(exist_ok=True)
    out.write_text(svg, encoding="utf-8")
    print(f"wrote {out} ({len(awards)} awards)")


if __name__ == "__main__":
    main()
