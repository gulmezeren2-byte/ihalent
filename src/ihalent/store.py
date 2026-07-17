"""Award storage: JSON Lines in, Award objects out.

JSONL is the interchange format on purpose. It is the boundary between however
you collected the data (ihale-mcp, the bundled fetcher, a hand-built export)
and the analytics core, which neither knows nor cares where the awards came
from. One award per line, deduplicated by İKN on load — the last line wins, so
re-collecting to refresh a record is safe.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

from ihalent.model import Award


def load_awards(path: str | Path) -> list[Award]:
    """Read a JSONL file of awards, de-duplicating by İKN (last wins)."""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Award file not found: {p}")
    by_ikn: dict[str, Award] = {}
    for lineno, line in enumerate(p.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{p}:{lineno}: not valid JSON: {exc}") from exc
        if "ikn" not in record:
            raise ValueError(f"{p}:{lineno}: award record has no 'ikn' field")
        award = Award.from_dict(record)
        by_ikn[award.ikn] = award
    return list(by_ikn.values())


def dump_awards(awards: Iterable[Award], path: str | Path) -> int:
    """Write awards as JSONL. Returns how many were written."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with p.open("w", encoding="utf-8") as f:
        for a in awards:
            f.write(json.dumps(a.to_dict(), ensure_ascii=False) + "\n")
            n += 1
    return n
