"""Read result notices from the Kamu İhale Bülteni (Public Procurement Bulletin).

KİK publishes every tender result in a daily bulletin, one file per tender type,
on EKAP's bulletin page. That bulletin is the statutory place of publication
(Law 4734, Art. 47), it needs no login, and it prints each result notice in full:
estimate, contract price, winner, bid counts.

A day's download is a ZIP with two PDFs; the one named ``*_SONUC.pdf`` holds the
result notices. Each notice is a two-column form — labels on the left, a ``:``
column, values on the right — and the columns do **not** line up row by row: in a
multi-line cell the ``:`` sits in the vertical middle, a long label wraps on its
own schedule, and a value can run onto the next page. So nothing here pairs by
row. The page is split into a label stream and a value stream, the value stream
is cut into cells by line spacing, each cell is tied to the one ``:`` it holds,
and the k-th label is paired with the k-th cell. A notice where those counts
disagree is rejected, never guessed.

Everything below the PDF boundary works on plain word lists, so it is tested
without a PDF library. Opening a PDF needs the optional extra:
``pip install "ihalent[bulletin]"``.

What was verified: the 13 November 2026 works (yapım) bulletin — 86 of 86 notices
read, and the İKN list matched the bulletin's own table of contents. The goods,
service and consultancy bulletins use the same form but were not checked.
"""

from __future__ import annotations

import io
import re
import zipfile
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from ihalent.ingest import _merge_lots
from ihalent.model import Award, TenderType
from ihalent.parse import _fold, parse_money_tr, split_winners

# Page bands, as fractions of the page height (A4: header ends ~70pt, footer
# starts ~790pt). The running header and the footer are dropped before parsing.
HEADER_FRACTION = 0.083
FOOTER_FRACTION = 0.938

LINE_TOLERANCE = 2.0  # words this close vertically are one line
CELL_GAP = 13.0  # lines inside a cell are ~11.5pt apart; rows are ~14.5pt apart
COLON_TOLERANCE = 1.0

_LABEL_START = re.compile(r"^[a-zçğıöşü]\)\s", re.IGNORECASE)
_PART_START = re.compile(r"^(\d)-\s")
# An İKN can carry a numbered suffix ('2026/1007522-4', services bulletin of 13
# November 2026); it is kept as printed, so such a notice is never merged into
# another.
_IKN = re.compile(r"\b(\d{4}/\d{5,}(?:-\d+)?)\b")
_IKN_FULL = re.compile(r"\d{4}/\d{5,}(?:-\d+)?")
_MONEY_FULL = re.compile(r"[\d.]+,\d{2}\s*(TRY|TL|USD|EUR)")
_MONEY_LIRA = re.compile(r"[\d.]+,\d{2}\s*(TRY|TL)")
# A tender priced in another currency prints its estimate in lira with the
# original beside it: '196.199.505,60 TRY (3.664.000,00 EUR)' (goods, 13 Nov 2026).
_LIRA_WITH_FX = re.compile(r"([\d.]+,\d{2}\s*(?:TRY|TL))\s*\([\d.]+,\d{2}\s*(?:USD|EUR)\)")
# How a notice says there is no estimate (both seen in the works bulletin of
# 12 November 2026). Only these exact forms: anything else is still rejected.
_NO_ESTIMATE = re.compile(
    r"-\s*(TRY|TL|USD|EUR)"
    r"|İhalenin ilgili mevzuat gereğince yaklaşık maliyeti bulunmamaktadır\.?"
)
_DATE_FULL = re.compile(r"\d{2}\.\d{2}\.\d{4}")
_INT_FULL = re.compile(r"\d+")
_ADDRESS_HINT = re.compile(r"\bMah\.|\bSk\.|\bNo:")
_SKIP_HEADINGS = (
    "A- 4734", "B- 4734", "1. İHALE SONUÇ", "1.1. ", "1. İSTİSNA", "2. KAPSAM",
    "2.1. ", "1. KAPSAM",
)


class BulletinError(ValueError):
    """The file is not a bulletin this module can read."""


class MissingExtra(ImportError):
    """Reading a PDF needs the optional ``bulletin`` extra."""


@dataclass(frozen=True)
class Word:
    page: int
    x0: float
    top: float
    bottom: float
    text: str


@dataclass
class Line:
    page: int
    top: float
    words: list[Word]

    @property
    def text(self) -> str:
        return _join(self.words)


@dataclass
class BulletinNotice:
    """One result notice: header context plus its (part, label, value) fields.

    Parts follow the form: "0" is the İKN row, "1" the tender, "2" the work,
    "3" the bids, "4" the contract. The winner's address row is dropped on
    purpose — nothing downstream needs it, and it is personal data for a sole
    trader."""

    ikn: str
    section: str  # "4734" (under the law), "istisna" (exempt), "kapsam-disi" (outside)
    page: int
    title: str | None
    authority: str | None
    fields: list[tuple[str, str, str]]

    def value(self, part: str, label: str) -> str | None:
        want = _fold(label)
        for p, lab, val in self.fields:
            if p == part and _fold(lab) == want:
                return val
        return None

    def has_label(self, prefix: str) -> bool:
        want = _fold(prefix)
        return any(_fold(lab).startswith(want) for _, lab, _ in self.fields)


@dataclass
class Rejection:
    position: int  # n-th notice in the file, from 1
    page: int
    reason: str


@dataclass
class BulletinRead:
    """What one result PDF yielded, with the evidence to trust it or not."""

    source: str
    notices: list[BulletinNotice] = field(default_factory=list)
    rejected: list[Rejection] = field(default_factory=list)
    toc_ikns: list[str] = field(default_factory=list)

    @property
    def missing(self) -> list[str]:
        """İKNs the table of contents lists that no read notice accounts for."""
        left = Counter(self.toc_ikns) - Counter(n.ikn for n in self.notices)
        return sorted(left.elements())

    @property
    def unlisted(self) -> list[str]:
        """Read notices whose İKN the table of contents does not list."""
        left = Counter(n.ikn for n in self.notices) - Counter(self.toc_ikns)
        return sorted(left.elements())

    @property
    def complete(self) -> bool:
        return bool(self.toc_ikns) and not (self.rejected or self.missing or self.unlisted)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "notices": len(self.notices),
            "rejected": [r.__dict__ for r in self.rejected],
            "toc_listed": len(self.toc_ikns),
            "missing": self.missing,
            "unlisted": self.unlisted,
            "complete": self.complete,
        }


# -- PDF boundary ---------------------------------------------------------------


def words_from_pdf(source: str | Path | io.BytesIO) -> list[Word]:
    """Every word on every page, minus the running header and footer."""
    try:
        import pdfplumber  # optional extra, imported on use
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise MissingExtra(
            'Reading bulletin PDFs needs the optional extra: pip install "ihalent[bulletin]"'
        ) from exc
    out: list[Word] = []
    with pdfplumber.open(source) as pdf:
        for number, page in enumerate(pdf.pages, start=1):
            low, high = page.height * HEADER_FRACTION, page.height * FOOTER_FRACTION
            for w in page.extract_words(x_tolerance=1.5):
                if low < w["top"] < high:
                    out.append(Word(number, w["x0"], w["top"], w["bottom"], w["text"]))
    return out


def result_pdfs(path: str | Path) -> list[tuple[str, bytes]]:
    """The result-notice PDFs in a downloaded bulletin (a ZIP) or a bare PDF."""
    p = Path(path)
    data = p.read_bytes()
    if data[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            found = [
                (name, z.read(name))
                for name in z.namelist()
                if name.upper().endswith("_SONUC.PDF")
            ]
        if not found:
            raise BulletinError(f"{p.name}: the archive holds no *_SONUC.pdf result file")
        return found
    if data[:4] == b"%PDF":
        return [(p.name, data)]
    raise BulletinError(f"{p.name}: neither a bulletin ZIP nor a PDF")


def read_bulletin(path: str | Path) -> list[BulletinRead]:
    """Read every result PDF in a bulletin file."""
    return [
        read_words(words_from_pdf(io.BytesIO(data)), source=name)
        for name, data in result_pdfs(path)
    ]


# -- Layout -------------------------------------------------------------------


def _join(words: Iterable[Word]) -> str:
    return " ".join(w.text for w in words).strip()


def lines_from_words(words: Iterable[Word]) -> list[Line]:
    """Group words into lines, in reading order across pages."""
    lines: list[Line] = []
    ordered = sorted(words, key=lambda w: (w.page, round(w.top / LINE_TOLERANCE), w.x0))
    for w in ordered:
        last = lines[-1] if lines else None
        if last and last.page == w.page and abs(w.top - last.words[0].top) <= LINE_TOLERANCE:
            last.words.append(w)
        else:
            lines.append(Line(w.page, w.top, [w]))
    for line in lines:
        line.words.sort(key=lambda w: w.x0)
    return lines


def colon_column(lines: Sequence[Line]) -> float | None:
    """x of the stand-alone ':' that opens every value (the most common one)."""
    xs = Counter(round(w.x0) for line in lines for w in line.words if w.text == ":")
    return float(xs.most_common(1)[0][0]) if xs else None


@dataclass
class _RawNotice:
    section: str
    page: int
    lines: list[Line]


def _split_notices(lines: Sequence[Line]) -> tuple[list[_RawNotice], list[Line]]:
    """Cut at every 'SONUÇ İLANI' heading. Returns the notices and the lines before
    the first one (the table of contents)."""
    notices: list[_RawNotice] = []
    preamble: list[Line] = []
    section = "4734"
    for line in lines:
        upper = line.text.upper()
        # The table of contents repeats the section headings, so the body's own
        # "A-" heading resets the state before the first notice.
        if upper.startswith("A- 4734 SAYILI KANUN KAPSAMINDAKİ"):
            section = "4734"
        if "İSTİSNA SONUÇLARININ" in upper:
            section = "istisna"
        if "KAPSAM DIŞI SONUÇLARININ" in upper:
            section = "kapsam-disi"
        if upper == "SONUÇ İLANI":
            notices.append(_RawNotice(section, line.page, []))
        elif notices:
            notices[-1].lines.append(line)
        else:
            preamble.append(line)
    return notices, preamble


def _value_cells(rows: Sequence[tuple[int, list[Word]]], colon_x: float) -> list[str]:
    """Cut the right-hand column into cells and return one value per ':'.

    A ':' comes either first on a cell's first line or alone in a cell's vertical
    middle. A new cell starts on a new page or where the line spacing widens; a
    cell that opens a page with no ':' of its own continues the previous page's
    value, and one that closes a page with no ':' is the start of the next page's
    first cell (its label and ':' went over the page break). Every cell must end
    up with exactly one ':'."""
    texts: list[dict[str, Any]] = []
    lone: list[tuple[int, float]] = []
    for page, ws in rows:
        leads = ws[0].text == ":" and abs(ws[0].x0 - colon_x) <= COLON_TOLERANCE
        if leads and len(ws) == 1:
            lone.append((page, (ws[0].top + ws[0].bottom) / 2))
            continue
        texts.append({
            "page": page, "top": ws[0].top, "bottom": max(w.bottom for w in ws),
            "colon": leads, "text": _join(ws[1:] if leads else ws),
        })

    cells: list[dict[str, Any]] = []
    for t in texts:
        last = cells[-1] if cells else None
        if last is None or t["page"] != last["page"] or t["top"] - last["last_top"] > CELL_GAP:
            cells.append({
                "page": t["page"], "top": t["top"], "bottom": t["bottom"],
                "last_top": t["top"], "colons": int(t["colon"]), "parts": [t["text"]],
                "opens_page": last is not None and t["page"] != last["page"],
            })
        else:
            last["parts"].append(t["text"])
            last["last_top"], last["bottom"] = t["top"], t["bottom"]
            last["colons"] += int(t["colon"])

    for page, middle in lone:
        hits = [
            c for c in cells
            if c["page"] == page
            and c["top"] - LINE_TOLERANCE <= middle <= c["bottom"] + LINE_TOLERANCE
        ]
        if len(hits) > 1:
            raise BulletinError("a ':' falls inside two value cells")
        if hits:
            hits[0]["colons"] += 1
        else:  # a ':' with nothing beside it: an empty value
            cells.append({
                "page": page, "top": middle, "bottom": middle, "last_top": middle,
                "colons": 1, "parts": [], "opens_page": False,
            })
    cells.sort(key=lambda c: (c["page"], c["top"]))

    merged: list[dict[str, Any]] = []
    for c in cells:
        prev = merged[-1] if merged else None
        if c["opens_page"] and c["colons"] == 0 and prev:
            prev["parts"].extend(c["parts"])  # value ran onto this page
        elif c["opens_page"] and c["colons"] == 1 and prev and prev["colons"] == 0:
            c["parts"] = prev["parts"] + c["parts"]  # it began at the foot of the last
            merged[-1] = c
        else:
            merged.append(c)
    bad = [c for c in merged if c["colons"] != 1]
    if bad:
        preview = " ".join(bad[0]["parts"])[:40]
        raise BulletinError(
            f"{len(bad)} value cell(s) without exactly one ':' (first: {preview!r})"
        )
    return [" ".join(c["parts"]).strip() for c in merged]


def _title_and_authority(header: Sequence[str]) -> tuple[str | None, str | None, str | None]:
    """The header reads 'N. İKN TITLE', then the title again, then the authority.
    Line breaks fall differently in the two copies, so compare without spaces.
    A line ending in a hyphenated fragment ('1978-ABC-') continues the next one."""
    text = ""
    for line in header:
        last = text.rsplit(" ", 1)[-1]
        glue = "" if len(last) > 1 and last.endswith("-") else " "
        text = (text + glue + line) if text else line
    m = re.match(r"^\d+\.\s+(\d{4}/\d{5,}(?:-\d+)?)\s+(.*)$", text)
    if not m:
        return None, None, None
    ikn, body = m.group(1), m.group(2)
    squeezed = re.sub(r"\s+", "", body)
    for size in range(len(squeezed) // 2, 4, -1):  # a "repeat" under 5 chars is chance
        if squeezed[:size] == squeezed[size:2 * size]:
            break
    else:
        return ikn, None, None

    def cut(s: str, n: int) -> tuple[str, str]:
        seen = 0
        for i, ch in enumerate(s):
            if not ch.isspace():
                seen += 1
                if seen == n:
                    return s[: i + 1], s[i + 1:]
        return s, ""

    title, rest = cut(body, size)
    _, authority = cut(rest, size)
    tidy = re.sub(r"\s+", " ", authority).strip()
    return ikn, re.sub(r"\s+", " ", title).strip(), tidy or None


def _type_problems(fields: Sequence[tuple[str, str, str]]) -> list[str]:
    """Each value must look like what its label promises; a one-cell shift fails here."""
    problems = []
    for part, label, value in fields:
        lab = _fold(label)
        if not value:
            continue
        if "yaklasik maliyeti" in lab:
            ok = bool(
                _MONEY_FULL.fullmatch(value)
                or _NO_ESTIMATE.fullmatch(value)
                or _LIRA_WITH_FX.fullmatch(value)
            )
        elif part == "4" and lab == "bedeli":
            ok = bool(_MONEY_FULL.fullmatch(value))
        elif lab == "tarihi":
            ok = bool(_DATE_FULL.fullmatch(value))
        elif "teklif sayisi" in lab or "indiren sayisi" in lab:
            ok = bool(_INT_FULL.fullmatch(value))
        elif lab == "ihale kayit numarasi":
            ok = bool(_IKN_FULL.fullmatch(value))
        elif lab in ("yuklenicisi", "yuklenici"):
            ok = not _ADDRESS_HINT.search(value)  # an address spilled into the winner
        else:
            continue
        if not ok:
            problems.append(f"{label} does not look right: {value[:40]!r}")
    return problems


def _parse_notice(raw: _RawNotice, colon_x: float) -> BulletinNotice:
    left_limit = colon_x - COLON_TOLERANCE
    header: list[str] = []
    labels: list[dict[str, str]] = []
    right: list[tuple[int, list[Word]]] = []
    in_body = False
    for line in raw.lines:
        left = [w for w in line.words if w.x0 < left_limit]
        right_words = [w for w in line.words if w.x0 >= left_limit]
        left_text = _join(left)
        if not in_body:
            if left_text.startswith("İhale kayıt numarası"):
                in_body = True
            else:
                whole = line.text
                if _INT_FULL.fullmatch(whole) or whole.upper().startswith(_SKIP_HEADINGS):
                    continue  # the centred notice number, or a section heading
                header.append(whole)
                continue
        if left_text.startswith("Kamuoyuna saygıyla"):
            break  # end of the notice; what follows is the next one's number
        if right_words:
            right.append((line.page, right_words))
        if not left_text:
            continue
        part_m = _PART_START.match(left_text)
        if left_text.startswith("İhale kayıt numarası"):
            labels.append({"part": "0", "label": "İhale kayıt numarası"})
        elif part_m:
            labels.append({"part": part_m.group(1), "heading": left_text})
        elif _LABEL_START.match(left_text):
            part = next((e["part"] for e in reversed(labels) if "heading" in e), "0")
            labels.append({"part": part, "label": _LABEL_START.sub("", left_text)})
        elif labels:  # a wrapped label or heading
            key = "label" if "label" in labels[-1] else "heading"
            labels[-1][key] += " " + left_text

    values = _value_cells(right, colon_x)
    named = [e for e in labels if "label" in e]
    if len(named) != len(values):
        raise BulletinError(f"{len(named)} labels but {len(values)} values")
    fields = []
    for e, v in zip(named, values, strict=True):
        label = e["label"].strip()
        if "adresi" in _fold(label):
            continue  # the winner's address: not needed, and personal for a sole trader
        fields.append((e["part"], label, re.sub(r"\s*-->\s*$", "", v).strip()))
    problems = _type_problems(fields)
    if problems:
        raise BulletinError("; ".join(problems))
    ikn = next((v for p, lab, v in fields if p == "0"), None)
    if not ikn:
        raise BulletinError("no İKN row")
    head_ikn, title, authority = _title_and_authority(header)
    if head_ikn and head_ikn != ikn:
        raise BulletinError(f"header İKN {head_ikn} differs from the form's {ikn}")
    return BulletinNotice(ikn, raw.section, raw.page, title, authority, fields)


def read_words(words: Iterable[Word], *, source: str = "") -> BulletinRead:
    """Parse one result PDF's words into notices, rejections and its table of contents."""
    lines = lines_from_words(words)
    raw_notices, preamble = _split_notices(lines)
    result = BulletinRead(source=source)
    result.toc_ikns = [m for line in preamble for m in _IKN.findall(line.text)]
    colon_x = colon_column(lines)
    if colon_x is None:
        if raw_notices:
            result.rejected = [
                Rejection(i, r.page, "no ':' column found")
                for i, r in enumerate(raw_notices, start=1)
            ]
        return result
    for i, raw in enumerate(raw_notices, start=1):
        try:
            result.notices.append(_parse_notice(raw, colon_x))
        except BulletinError as exc:
            result.rejected.append(Rejection(i, raw.page, str(exc)))
    return result


# -- Awards -------------------------------------------------------------------


def _tender_type(raw: str | None) -> TenderType:
    folded = _fold(raw or "")
    if "yapim" in folded:
        return TenderType.WORKS
    if "danismanlik" in folded:
        return TenderType.CONSULTING
    if "hizmet" in folded:
        return TenderType.SERVICE
    if "mal" in folded:
        return TenderType.GOODS
    return TenderType.UNKNOWN


def _int_or_none(value: str | None) -> int | None:
    return int(value) if value and _INT_FULL.fullmatch(value) else None


def _lira(value: str | None) -> float | None:
    """A lira amount, or None. A notice that says there is no estimate has none,
    and an amount in euros or dollars is not lira: no exchange rate is guessed."""
    if not value:
        return None
    fx = _LIRA_WITH_FX.fullmatch(value)
    if fx:
        value = fx.group(1)  # the lira figure printed beside the original
    return parse_money_tr(value) if _MONEY_LIRA.fullmatch(value) else None


def _iso_date(value: str | None) -> str | None:
    if not value or not _DATE_FULL.fullmatch(value):
        return None
    d, m, y = value.split(".")
    return f"{y}-{m}-{d}"


def is_lot_notice(notice: BulletinNotice) -> bool:
    """A notice for one lot of a tender awarded in parts (kısmi teklif): the form
    then carries 'Sözleşmeye Esas Kısımlarının Yaklaşık Maliyeti'."""
    return notice.has_label("Sözleşmeye Esas Kısım")


def award_from_notice(notice: BulletinNotice) -> Award:
    """One notice as an Award, read field by field from its own section."""
    estimate = notice.value("1", "Yaklaşık Maliyeti")
    contract = notice.value("4", "Bedeli")
    winner_cell = notice.value("4", "Yüklenicisi") or notice.value("4", "Yüklenici")
    downloaders = next(
        (v for p, lab, v in notice.fields if p == "3" and _fold(lab).startswith("dokumani")),
        None,
    )
    winner: str | None = None
    winners_all: list[str] = []
    is_jv = False
    if winner_cell:
        winner, winners_all, is_jv = split_winners(winner_cell)
    return Award(
        ikn=notice.ikn,
        title=notice.title,
        authority=notice.authority,
        province=None,  # the bulletin has no province field; it is not inferred
        tender_type=_tender_type(notice.value("1", "Türü")),
        estimate_try=_lira(estimate),
        contract_try=_lira(contract),  # empty for a contract priced in EUR or USD
        winner=winner,
        winners_all=winners_all,
        is_joint_venture=is_jv,
        downloaders=_int_or_none(downloaders),
        bid_count=_int_or_none(notice.value("3", "Toplam Teklif Sayısı")),
        valid_bid_count=_int_or_none(notice.value("3", "Toplam Geçerli Teklif Sayısı")),
        result_date=_iso_date(notice.value("4", "Tarihi")),  # the contract date
        cancelled=winner is None and contract is None,
        lots_unverified=is_lot_notice(notice),
    )


def awards_from_reads(reads: Iterable[BulletinRead]) -> list[Award]:
    """Merge the notices of any number of bulletins into one award per İKN.

    Run it over *every* bulletin collected so far, not one day at a time: a
    tender's lots are published on different days, and a per-day file would
    overwrite the earlier lots (awards de-duplicate by İKN on load). A file read
    twice (the same bulletin as a ZIP and as its extracted PDF) counts once, by
    its name; within a file every notice counts, since two lots can carry the
    same winner and price. A tender with lots keeps its estimate and summed
    contracts but no discount, because no bulletin says when the last lot has
    been printed."""
    seen_sources: set[str] = set()
    by_ikn: dict[str, list[BulletinNotice]] = {}
    for read in reads:
        if read.source and read.source in seen_sources:
            continue
        seen_sources.add(read.source)
        for n in read.notices:
            by_ikn.setdefault(n.ikn, []).append(n)
    awards = []
    for notices in by_ikn.values():
        parts = [award_from_notice(n) for n in notices]
        if len(parts) == 1:
            awards.append(parts[0])
            continue
        awards.append(replace(_merge_lots(parts), lots_unverified=True))
    return awards
