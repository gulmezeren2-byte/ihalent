"""Parse an EKAP result notice (Sonuç İlanı) into an Award.

The result notice is a stable markdown table. This module turns it into a
structured record with regexes and nothing cleverer — no ML, no heuristics
that might "usually" work. When a field is not found, it stays None; a parser
for procurement data that quietly fills blanks is worse than useless.

The input is the markdown EKAP/ihale-mcp returns for an announcement of type
"Sonuç İlanı". Feeding it any other announcement type raises NotAResultNotice
rather than returning a hollow record.
"""

from __future__ import annotations

import re

from ihalent.model import Award, TenderType

_IKN = re.compile(r"(\d{4}/\d{5,})")
_MONEY = re.compile(r"([\d.]+,\d{2})\s*(?:TRY|TL)?", re.IGNORECASE)

# Turkish 'İ'.lower() yields 'i' + a combining dot, which never matches a
# plain 'i'; and 'I'.lower() is 'i' while the letter meant 'ı'. Case-folding
# for *search* therefore has to be explicit. We fold every dotted/dotless i to
# plain 'i' and the other Turkish letters to their ASCII base — lossy on
# purpose, since this fold is only ever used to compare labels, never to store.
_FOLD = str.maketrans(
    {
        "İ": "i", "I": "i", "ı": "i", "i": "i",
        "ş": "s", "Ş": "s",
        "ğ": "g", "Ğ": "g",
        "ü": "u", "Ü": "u",
        "ö": "o", "Ö": "o",
        "ç": "c", "Ç": "c",
    }
)


def _fold(text: str) -> str:
    return text.translate(_FOLD).lower()


class NotAResultNotice(ValueError):
    """The text is not a Sonuç İlanı (result notice)."""


def parse_money_tr(text: str) -> float | None:
    """'2.783.270,09 TRY' -> 2783270.09. Turkish grouping: '.' thousands,
    ',' decimal. Returns None if no money-shaped token is present."""
    m = _MONEY.search(text)
    if not m:
        return None
    token = m.group(1)
    return float(token.replace(".", "").replace(",", "."))


def _row(label: str, text: str) -> str | None:
    """Value cell of a two/three-column markdown row whose label matches.

    EKAP rows look like: ``| **d)** Yaklaşık Maliyeti | : | 2.783.270,09 TRY |``
    We match the label anywhere in the first cell, then take the last
    non-empty pipe-delimited cell on that line."""
    folded_label = _fold(label)
    for line in text.splitlines():
        if folded_label in _fold(line) and "|" in line:
            cells = [c.strip() for c in line.split("|")]
            cells = [c for c in cells if c and c != ":"]
            if not cells:
                continue
            # The label sits in the first surviving cell; the value is the last.
            value = cells[-1]
            if folded_label in _fold(value) and len(cells) == 1:
                continue
            return value
    return None


def _int(text: str | None) -> int | None:
    if text is None:
        return None
    m = re.search(r"\d+", text.replace(".", ""))
    return int(m.group()) if m else None


def is_result_notice(md: str) -> bool:
    folded = _fold(md)
    return "sonuc ilani" in folded or ("sozlesmenin" in folded and "yuklenici" in folded)


def split_winners(raw: str) -> tuple[str | None, list[str], bool]:
    """Split a winner cell into (lead, all_members, is_joint_venture).

    JV cells read 'PARTY A, PARTY B ... İş Ortaklığı'. Company names contain
    no commas in EKAP's rendering, so comma is a safe member separator once
    the trailing 'İş Ortaklığı' marker is stripped."""
    text = raw.strip()
    is_jv = "is ortakligi" in _fold(text)
    cleaned = re.sub(r"\s*İş\s+Ortaklığı\s*$", "", text, flags=re.IGNORECASE).strip()
    members = [m.strip() for m in cleaned.split(",") if m.strip()]
    if not members:
        return None, [], is_jv
    return members[0], members, is_jv


def parse_result_notice(
    md: str,
    *,
    title: str | None = None,
    authority: str | None = None,
    province: str | None = None,
    tender_type: TenderType = TenderType.UNKNOWN,
) -> Award:
    """Parse one result-notice markdown blob into an Award.

    The optional fields let a caller pass context the notice body does not
    repeat (EKAP carries title/authority/province on the search record, not
    always in the notice text)."""
    if not is_result_notice(md):
        raise NotAResultNotice(
            "This does not look like a Sonuç İlanı (no result markers found). "
            "Pass the result announcement, not the tender notice or pre-notice."
        )

    ikn_m = _IKN.search(md)
    if not ikn_m:
        raise NotAResultNotice("No İKN (tender reference number) found in the text.")

    estimate_cell = _row("Yaklaşık Maliyeti", md)
    contract_cell = _row("Bedeli", md)
    winner_cell = _row("Yüklenicisi", md)

    winner: str | None = None
    winners_all: list[str] = []
    is_jv = False
    if winner_cell:
        winner, winners_all, is_jv = split_winners(winner_cell)

    # A result notice with no winner and no contract value is a cancellation.
    cancelled = winner is None and contract_cell is None

    return Award(
        ikn=ikn_m.group(1),
        title=title,
        authority=authority,
        province=province,
        tender_type=tender_type,
        estimate_try=parse_money_tr(estimate_cell) if estimate_cell else None,
        contract_try=parse_money_tr(contract_cell) if contract_cell else None,
        winner=winner,
        winners_all=winners_all,
        is_joint_venture=is_jv,
        downloaders=_int(_row("indiren sayısı", md)),
        bid_count=_int(_row("Toplam Teklif Sayısı", md)),
        valid_bid_count=_int(_row("Geçerli Teklif Sayısı", md)),
        result_date=_parse_date(_row("Tarihi", md)),
        cancelled=cancelled,
    )


def _parse_date(cell: str | None) -> str | None:
    """'26.01.2026' -> '2026-01-26'. Leaves anything else untouched."""
    if not cell:
        return None
    m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", cell)
    if not m:
        return None
    d, mo, y = m.groups()
    return f"{y}-{mo}-{d}"
