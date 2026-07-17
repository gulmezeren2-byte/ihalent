"""Build examples/sample-awards.jsonl from the real notices in notices/.

The .md files here are result notices pulled live from EKAP via ihale-mcp in
December-2025/January-2026 — four real awards across four kinds of authority
(a provincial administration, a state water works, a university, a
municipality). We ship the notices, not a redistributed dataset: the script
parses them into the JSONL the analytics commands read, exactly as a user
would with their own collected notices.

The `MANIFEST` supplies the context EKAP keeps on the search record rather than
in the notice body (authority, province, tender type). Re-run after editing:

    python build_sample.py
"""

from __future__ import annotations

from pathlib import Path

from ihalent.model import TenderType
from ihalent.parse import parse_result_notice
from ihalent.store import dump_awards

HERE = Path(__file__).parent

# ikn -> (authority, province, tender_type). Sourced from the EKAP search record.
MANIFEST = {
    "2025/2337797": ("Ağrı İl Özel İdaresi", "Ağrı", TenderType.WORKS),
    "2025/2198370": ("DSİ 14. Bölge Müdürlüğü", "İstanbul", TenderType.WORKS),
    "2025/2388267": ("İstanbul Üniversitesi-Cerrahpaşa", "İstanbul", TenderType.WORKS),
    "2025/2174700": ("Esenler Belediyesi", "İstanbul", TenderType.WORKS),
}


def main() -> None:
    awards = []
    for md_path in sorted((HERE / "notices").glob("*.md")):
        ikn = md_path.stem.replace("-", "/", 1)
        authority, province, ttype = MANIFEST.get(ikn, (None, None, TenderType.UNKNOWN))
        award = parse_result_notice(
            md_path.read_text(encoding="utf-8"),
            authority=authority,
            province=province,
            tender_type=ttype,
        )
        awards.append(award)

    out = HERE / "sample-awards.jsonl"
    n = dump_awards(awards, out)
    print(f"wrote {out.name}: {n} awards")
    for a in awards:
        disc = f"{a.discount_pct:+.1f}%" if a.discount_pct is not None else "n/a"
        print(f"  {a.ikn}  {disc:>7}  {a.valid_bid_count} valid bids  {a.winner}")


if __name__ == "__main__":
    main()
