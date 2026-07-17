"""Build examples/sample-awards.jsonl from the real data in this folder.

Two real sources, both collected from EKAP via ihale-mcp in
December-2025/January-2026, shipped as-is (we ship the collected notices, not a
redistributed dataset):

  notices/*.md              four result notices across four authority types,
                            including İstanbul Üniversitesi-Cerrahpaşa's
                            emergency award *above* its estimate (−2.96% kırım)
  istanbul-yapim-2025.json  an ihale-mcp bundle of six İstanbul construction
                            tenders (municipalities, a bank, a university, the
                            water utility) — fed through ihalent's own ingest,
                            exactly the path a user takes with their own bundle

The `MANIFEST` supplies the context EKAP keeps on the search record rather than
in the notice body (authority, province, tender type) for the loose .md files;
the bundle already carries its own tender context. Re-run after editing:

    python build_sample.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from ihalent.ingest import ingest_bundle
from ihalent.model import TenderType
from ihalent.parse import parse_result_notice
from ihalent.store import dump_awards, load_awards

# Winner names contain Turkish letters; on a legacy Windows console code page a
# plain print() of them raises UnicodeEncodeError. Degrade instead of crashing.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

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

    # 1) the loose result notices
    for md_path in sorted((HERE / "notices").glob("*.md")):
        ikn = md_path.stem.replace("-", "/", 1)
        authority, province, ttype = MANIFEST.get(ikn, (None, None, TenderType.UNKNOWN))
        awards.append(
            parse_result_notice(
                md_path.read_text(encoding="utf-8"),
                authority=authority,
                province=province,
                tender_type=ttype,
            )
        )

    # 2) the ihale-mcp bundle, through the real ingest path
    bundle = json.loads((HERE / "istanbul-yapim-2025.json").read_text(encoding="utf-8"))
    awards.extend(ingest_bundle(bundle))

    # dump (dedupes by İKN on load), then reload so the sample is exactly what
    # the analytics commands will see
    out = HERE / "sample-awards.jsonl"
    dump_awards(awards, out)
    final = load_awards(out)
    dump_awards(final, out)

    print(f"wrote {out.name}: {len(final)} awards")
    for a in sorted(final, key=lambda x: (x.discount_pct is None, x.discount_pct or 0)):
        disc = f"{a.discount_pct:+.1f}%" if a.discount_pct is not None else "n/a"
        lots = f" [{a.lot_count} lots]" if a.is_partial else ""
        print(f"  {a.ikn}  {disc:>7}{lots}  {a.winner}")


if __name__ == "__main__":
    main()
