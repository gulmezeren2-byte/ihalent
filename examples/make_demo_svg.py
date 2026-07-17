"""Regenerate docs/demo.svg from the sample dataset.

The README screenshot is not a mock-up: it is `ihalent overview` +
`ihalent discounts --by authority` rendered over examples/sample-awards.jsonl.
Re-run after changing the sample or the renderers so the README never lies
about what the tool prints.

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
from rich.table import Table

from ihalent.analytics import by_group, overview
from ihalent.render import fmt_pct, render_overview
from ihalent.store import load_awards

ROOT = Path(__file__).parent.parent


def main() -> None:
    awards = load_awards(ROOT / "examples" / "sample-awards.jsonl")
    console = Console(record=True, width=90)

    render_overview(overview(awards), console)

    groups = by_group(awards, "authority")
    if groups:
        table = Table(title="Mean discount by authority", title_justify="left")
        table.add_column("authority")
        table.add_column("mean", justify="right")
        table.add_column("awards", justify="right")
        for g in groups:
            table.add_row(
                g.label, fmt_pct(g.mean), f"{g.coverage.used}/{g.coverage.considered}"
            )
        console.print(table)

    svg = console.export_svg(title="ihalent")
    # Drop the CDN font-face so the SVG is self-contained on GitHub.
    svg = re.sub(r"@font-face\s*\{[^}]*?\}", "", svg, flags=re.DOTALL)
    out = ROOT / "docs" / "demo.svg"
    out.parent.mkdir(exist_ok=True)
    out.write_text(svg, encoding="utf-8")
    print(f"wrote {out} ({len(awards)} awards)")


if __name__ == "__main__":
    main()
