"""Company-name normalization.

Firm-level analytics live or die on this: "ABC İNŞAAT LTD. ŞTİ." and
"ABC INSAAT LIMITED SIRKETI" must fold to the same key, or every firm's
history shatters across spelling variants and the numbers lie. The approach
is intentionally conservative — fold case, Turkish diacritics and the handful
of legal-form suffixes that are pure noise, and nothing else. Over-aggressive
normalization would merge genuinely different firms, which is the worse error
here: a watchdog would rather see two rows for one company than one row for two.
"""

from __future__ import annotations

import re

# Turkish -> ASCII, done explicitly so İ/ı map the way a Turkish reader expects
# rather than however the default lower() happens to behave.
_TR_MAP = str.maketrans(
    {
        "ç": "c", "Ç": "c",
        "ğ": "g", "Ğ": "g",
        "ı": "i", "I": "i", "İ": "i", "i": "i",
        "ö": "o", "Ö": "o",
        "ş": "s", "Ş": "s",
        "ü": "u", "Ü": "u",
    }
)

# Legal-form boilerplate that carries no identifying information. Order matters:
# longer forms first so "limited sirketi" is removed before "sirketi" alone.
_SUFFIXES = [
    "sanayi ve ticaret limited sirketi",
    "sanayi ve ticaret anonim sirketi",
    "insaat taahhut",
    "limited sirketi",
    "anonim sirketi",
    "ltd sti",
    "ltd. sti.",
    "a s",
    "san ve tic",
    "sanayi ticaret",
    "ve ticaret",
    "ve sanayi",
]


def normalize_company(name: str) -> str:
    """A folding key for grouping, NOT a pretty display name. Idempotent."""
    s = name.translate(_TR_MAP).lower()
    s = re.sub(r"[.\,\-/]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    for suffix in _SUFFIXES:
        if s.endswith(" " + suffix) or s == suffix:
            s = s[: -len(suffix)].strip()
    return re.sub(r"\s+", " ", s).strip()


def display_name(names: list[str]) -> str:
    """Pick a human-facing label for a group of raw spellings that share a key:
    the longest one, which usually carries the fullest legal form. Ties break
    on the first seen, so output is stable across runs."""
    if not names:
        return ""
    return max(names, key=lambda n: (len(n), names.index(n) * -1))
