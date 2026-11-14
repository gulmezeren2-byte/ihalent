"""Bulletin reader tests on synthetic pages.

The layout below reproduces the geometry measured on a real Kamu İhale Bülteni
result PDF (13 November 2026): labels from x≈75, the ':' column at x=242,
values from x≈248, 11.5pt between lines inside a cell and 14.5pt between rows,
and the ':' placed in the vertical middle of a multi-line cell. Every name and
number is invented; no real bulletin is stored in this repository.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ihalent import bulletin
from ihalent.bulletin import (
    BulletinRead,
    Word,
    awards_from_reads,
    read_words,
)
from ihalent.cli import app
from ihalent.model import Award, TenderType

LABEL_X, COLON_X, VALUE_X = 75.4, 242.0, 248.3
LINE, ROW = 11.5, 14.5


def _words(page: int, x: float, top: float, text: str) -> list[Word]:
    out = []
    for piece in text.split():
        out.append(Word(page, x, top, top + 10.0, piece))
        x += 6.0 * len(piece) + 4.0
    return out


class Page:
    """Lays out notices the way the bulletin does, on one tall virtual page."""

    def __init__(self) -> None:
        self.words: list[Word] = []
        self.top = 90.0

    def line(self, text: str, x: float = 180.0) -> None:
        self.words += _words(1, x, self.top, text)
        self.top += LINE

    def notice(
        self, number: int, ikn: str, title: str, authority: str, rows: list,
        header: list[str] | None = None,
    ) -> None:
        self.line(str(number), x=295.0)
        self.line("SONUÇ İLANI", x=264.5)
        # The header is "N. İKN TITLE", then the title again, then the authority;
        # ``header`` overrides the lines after the first to set where they break.
        lines = header or [title, title, authority]
        self.words += _words(1, 107.2, self.top, f"{number}.")
        self.words += _words(1, 178.0, self.top, f"{ikn} {lines[0]}")
        self.top += LINE
        for text in lines[1:]:
            self.line(text)
        self.top += 14.0
        for row in rows:
            self._row(*row)
        self.words += _words(1, LABEL_X, self.top, "Kamuoyuna saygıyla duyurulur.")
        self.top += 40.0

    def _row(self, kind: str, label: object = "", value: object = None, colon: str = "top") -> None:
        if kind == "part":
            self.words += _words(1, LABEL_X, self.top, str(label))
            self.top += ROW
            return
        labels = label if isinstance(label, list) else [label]
        if value is None:
            values: list[str] = []
        else:
            values = value if isinstance(value, list) else [value]
        n = max(len(labels), len(values), 1)
        start = self.top
        middle = start + (len(values) - 1) * LINE / 2 if values else start
        label_top = middle if colon == "middle" else start
        for i, lab in enumerate(labels):
            self.words += _words(1, LABEL_X, label_top + i * LINE, lab)
        colon_top = middle if colon == "middle" else start
        self.words.append(Word(1, COLON_X, colon_top, colon_top + 10.0, ":"))
        for i, val in enumerate(values):
            self.words += _words(1, VALUE_X, start + i * LINE, val)
        self.top = start + (n - 1) * LINE + ROW

    def paginate(self, limit: float = 760.0) -> list[Word]:
        """Move everything below ``limit`` onto page 2, as a page break would."""
        out = []
        for w in self.words:
            if w.top > limit:
                out.append(Word(2, w.x0, w.top - limit + 80.0, w.bottom - limit + 80.0, w.text))
            else:
                out.append(w)
        return out


def standard_rows(ikn: str, **over: object) -> list:
    return [
        ("field", "İhale kayıt numarası", ikn),
        ("part", "1- İhalenin"),
        ("field", "a) Tarihi", "02.10.2026"),
        ("field", "b) Türü", "Yapım işi"),
        ("field", "c) Usulü", "Açık"),
        ("field", "d) Yaklaşık Maliyeti", over.get("estimate", "1.000.000,00 TRY")),
        ("part", "2- İhale konusu yapım işinin"),
        ("field", "a) Adı", over.get("name", "Örnek Okul Onarımı")),
        ("field", "b) Yapılacağı yer", "Örnek Mahallesi"),
        ("field", "c) Süresi", "90"),
        ("part", "3- Teklifler"),
        ("field", ["a) Dokümanı EKAP üzerinden", "e-imza kullanarak indiren sayısı"], "9"),
        ("field", "b) Toplam Teklif Sayısı", "5"),
        ("field", "c) Toplam Geçerli Teklif Sayısı", "4"),
        ("field", ["d) Yerli istekli lehine", "fiyat avantajı uygulaması"], "Uygulanmamıştır"),
        ("part", "4- Sözleşmenin"),
        ("field", "a) Tarihi", "05.11.2026"),
        ("field", "b) Bedeli", over.get("contract", "800.000,00 TRY")),
        ("field", "c) Süresi", over.get("duration", "10.11.2026 - 08.02.2027")),
        ("field", "d) Yüklenicisi", over.get("winner", "Örnek Yapı Limited Şirketi")),
        ("field", "e) Yüklenicinin uyruğu", "Türkiye"),
        ("field", "f) Yüklenicinin adresi", ["Örnek Mah. Deneme Sk. No: 1", "Merkez/Örnekil"]),
    ]


def _replace(rows: list, label: str, new: tuple) -> list:
    return [new if r[0] == "field" and r[1] == label else r for r in rows]


def toc(*ikns: str) -> Page:
    page = Page()
    page.line("İÇİNDEKİLER", x=75.0)
    for i, ikn in enumerate(ikns, start=1):
        page.line(f"{i}. {ikn} ÖRNEK İŞ ........ 5", x=75.0)
    return page


def read(page: Page, words: list[Word] | None = None) -> BulletinRead:
    return read_words(words if words is not None else page.words, source="test.pdf")


def test_reads_a_plain_notice_into_an_award() -> None:
    page = toc("2026/1000001")
    page.notice(1, "2026/1000001", "ÖRNEK OKUL ONARIMI", "ÖRNEK BELEDİYESİ",
                standard_rows("2026/1000001"))
    r = read(page)
    assert r.complete, r.to_dict()
    (a,) = awards_from_reads([r])
    assert a.ikn == "2026/1000001"
    assert a.title == "ÖRNEK OKUL ONARIMI"
    assert a.authority == "ÖRNEK BELEDİYESİ"
    assert a.tender_type is TenderType.WORKS
    assert a.estimate_try == 1_000_000.0
    assert a.contract_try == 800_000.0
    assert a.discount_pct == 20.0
    assert a.winner == "Örnek Yapı Limited Şirketi"
    assert (a.downloaders, a.bid_count, a.valid_bid_count) == (9, 5, 4)
    # The contract date (part 4), not the tender date (part 1).
    assert a.result_date == "2026-11-05"
    # The bulletin has no province field; nothing is inferred.
    assert a.province is None


def test_a_multi_line_cell_with_the_colon_in_its_middle() -> None:
    # Two lines: the ':' sits alone between them. Three lines: it shares the middle one.
    rows = standard_rows("2026/1000002")
    rows = _replace(rows, "a) Adı", ("field", "a) Adı",
                                     ["Örnek İlçesi Yurt Binalarında Bakım", "ve Onarım İşleri"],
                                     "middle"))
    rows = _replace(rows, "d) Yüklenicisi", ("field", "d) Yüklenicisi",
                                              ["Birinci Örnek İnşaat Anonim Şirketi,",
                                               "İkinci Örnek Yapı Limited Şirketi",
                                               "İş Ortaklığı"], "middle"))
    page = toc("2026/1000002")
    page.notice(1, "2026/1000002", "BİNA İŞLERİ", "ÖRNEK MÜDÜRLÜĞÜ", rows)
    r = read(page)
    assert r.complete, r.to_dict()
    n = r.notices[0]
    assert n.value("2", "Adı") == "Örnek İlçesi Yurt Binalarında Bakım ve Onarım İşleri"
    # The estimate above it must not swallow the cell's first line.
    assert n.value("1", "Yaklaşık Maliyeti") == "1.000.000,00 TRY"
    (a,) = awards_from_reads([r])
    assert a.is_joint_venture
    assert a.winners_all == [
        "Birinci Örnek İnşaat Anonim Şirketi", "İkinci Örnek Yapı Limited Şirketi",
    ]


def test_a_wrapped_label_beside_a_long_value() -> None:
    rows = standard_rows("2026/1000003")
    rows.insert(5, ("field", ["d) Pazarlık Usulünün Seçilme", "Gerekçesi"],
                    ["Birinci satır", "ikinci satır", "üçüncü satır", "dördüncü satır"]))
    rows = _replace(rows, "d) Yaklaşık Maliyeti", ("field", "e) Yaklaşık Maliyeti",
                                                    "2.000.000,00 TRY -->"))
    page = toc("2026/1000003")
    page.notice(1, "2026/1000003", "ACİL ONARIM", "ÖRNEK İDARESİ", rows)
    r = read(page)
    assert r.complete, r.to_dict()
    n = r.notices[0]
    assert n.value("1", "Pazarlık Usulünün Seçilme Gerekçesi") == (
        "Birinci satır ikinci satır üçüncü satır dördüncü satır"
    )
    assert n.value("1", "Yaklaşık Maliyeti") == "2.000.000,00 TRY"  # the stray '-->' is gone


def test_an_empty_value_stays_empty() -> None:
    rows = _replace(standard_rows("2026/1000004"), "c) Süresi", ("field", "c) Süresi", None))
    page = toc("2026/1000004")
    page.notice(1, "2026/1000004", "İŞ", "İDARE", rows)
    r = read(page)
    assert r.complete, r.to_dict()
    assert r.notices[0].value("2", "Süresi") == ""


def test_a_value_that_runs_onto_the_next_page() -> None:
    rows = standard_rows("2026/1000005")
    rows = _replace(rows, "b) Yapılacağı yer", ("field", "b) Yapılacağı yer",
                                                 [f"{i}. Kısım Örnek Yeri" for i in range(1, 9)]))
    page = toc("2026/1000005")
    page.notice(1, "2026/1000005", "İŞ", "İDARE", rows)
    # Break the page in the middle of that cell.
    cut = next(w.top for w in page.words if w.text == "5.") - 1.0
    r = read(page, page.paginate(limit=cut))
    assert r.complete, r.to_dict()
    assert r.notices[0].value("2", "Yapılacağı yer").count("Kısım") == 8
    assert r.notices[0].value("2", "Süresi") == "90"


def test_a_value_that_starts_at_the_foot_of_a_page() -> None:
    # Goods bulletin of 13 November 2026: a long cell's first line is the last line
    # of a page, and its label and ':' are printed on the next page with the rest.
    rows = standard_rows("2026/1000022")
    rows = _replace(rows, "b) Yapılacağı yer", ("field", "b) Yapılacağı yer",
                                                 [f"{i}. Kısım Örnek Yeri" for i in range(1, 9)],
                                                 "middle"))
    page = toc("2026/1000022")
    page.notice(1, "2026/1000022", "İŞ", "İDARE", rows)
    cut = next(w.top for w in page.words if w.text == "2.") - 1.0  # only line 1 stays
    r = read(page, page.paginate(limit=cut))
    assert r.complete, r.to_dict()
    place = r.notices[0].value("2", "Yapılacağı yer")
    assert place.startswith("1. Kısım") and place.count("Kısım") == 8
    assert r.notices[0].value("2", "Adı") == "Örnek Okul Onarımı"


def test_the_winners_address_is_never_kept() -> None:
    page = toc("2026/1000006")
    page.notice(1, "2026/1000006", "İŞ", "İDARE", standard_rows("2026/1000006"))
    n = read(page).notices[0]
    assert all("adres" not in label.lower() for _, label, _ in n.fields)
    assert "Deneme Sk." not in json.dumps(n.fields, ensure_ascii=False)


def test_exempt_notices_use_their_own_template() -> None:
    rows = [
        ("field", "İhale kayıt numarası", "2026/1000007"),
        ("part", "1- İhalenin"),
        ("field", "a) Tarihi", "02.10.2026"),
        ("field", "b) Türü", "Yapım işi"),
        ("field", "c) Usulü", "4734 / 3-i"),
        ("field", "d) Yaklaşık Maliyeti", "500.000,00 TRY"),
        ("part", "2- İhale konusu yapım işinin"),
        ("field", "a) Adı", "Restorasyon"),
        ("part", "3- Teklifler"),
        ("field", "a) Toplam Teklif Sayısı", "3"),
        ("field", "b) Toplam Geçerli Teklif Sayısı", "2"),
        ("part", "4- Sözleşmenin"),
        ("field", "a) Tarihi", "05.11.2026"),
        ("field", "b) Bedeli", "450.000,00 TRY"),
        ("field", "c) Süresi", "10.11.2026 - 25.10.2027"),
        ("field", "d) Yüklenici", "Örnek Restorasyon Limited Şirketi"),
        ("field", "e) Yüklenicinin adresi", "Örnek Mah. No: 3"),
    ]
    page = toc("2026/1000007")
    page.line("1. İSTİSNA SONUÇLARININ İLANLARI", x=75.0)
    page.notice(1, "2026/1000007", "RESTORASYON", "ÖRNEK BAŞKANLIĞI", rows)
    r = read(page)
    assert r.complete, r.to_dict()
    assert r.notices[0].section == "istisna"
    (a,) = awards_from_reads([r])
    assert a.winner == "Örnek Restorasyon Limited Şirketi"
    assert a.downloaders is None  # not printed for exempt notices: unknown, not 0
    assert a.bid_count == 3


def _lot(ikn: str, contract: str, winner: str = "Örnek Yapı Limited Şirketi") -> list:
    rows = standard_rows(ikn, estimate="10.000.000,00 TRY", contract=contract, winner=winner)
    rows.insert(6, ("field", ["e) Sözleşmeye Esas Kısımlarının", "Yaklaşık Maliyeti"],
                    "10.000.000,00 TRY"))
    return rows


def test_lots_keep_their_numbers_but_get_no_discount() -> None:
    page = toc("2026/1000008", "2026/1000008")
    page.notice(1, "2026/1000008", "KISIMLI İŞ", "İDARE", _lot("2026/1000008", "2.000.000,00 TRY"))
    page.notice(2, "2026/1000008", "KISIMLI İŞ", "İDARE", _lot("2026/1000008", "3.000.000,00 TRY"))
    r = read(page)
    assert r.complete, r.to_dict()
    (a,) = awards_from_reads([r])
    assert a.lot_count == 2
    assert a.estimate_try == 10_000_000.0
    assert a.contract_try == 5_000_000.0
    # Other lots may come out on another day: comparing now would invent a 50% discount.
    assert a.lots_unverified
    assert a.discount_pct is None


def test_a_single_lot_seen_so_far_is_still_a_lot() -> None:
    page = toc("2026/1000009")
    page.notice(1, "2026/1000009", "KISIMLI İŞ", "İDARE", _lot("2026/1000009", "2.000.000,00 TRY"))
    (a,) = awards_from_reads([read(page)])
    assert a.lot_count == 1
    assert a.lots_unverified
    assert a.discount_pct is None


def test_lots_from_different_days_merge_and_repeats_count_once() -> None:
    day1, day2 = toc("2026/1000010"), toc("2026/1000010")
    day1.notice(1, "2026/1000010", "İŞ", "İDARE",
                _lot("2026/1000010", "2.000.000,00 TRY", winner="Birinci Yapı Ltd. Şti."))
    day2.notice(1, "2026/1000010", "İŞ", "İDARE",
                _lot("2026/1000010", "3.000.000,00 TRY", winner="İkinci İnşaat A.Ş."))
    r1 = read_words(day1.words, source="BULTEN_12112026_YAPIM_SONUC.pdf")
    r2 = read_words(day2.words, source="BULTEN_13112026_YAPIM_SONUC.pdf")
    (a,) = awards_from_reads([r1, r2, r1])  # day 1 read twice (ZIP and extracted PDF)
    assert a.lot_count == 2
    assert a.contract_try == 5_000_000.0
    # Each lot keeps its own winner and price, so a firm is credited only its lot.
    assert [(lot.winners, lot.contract_try) for lot in a.lots] == [
        (["Birinci Yapı Ltd. Şti."], 2_000_000.0),
        (["İkinci İnşaat A.Ş."], 3_000_000.0),
    ]


def test_two_identical_lots_in_one_file_both_count() -> None:
    # Two lots can go to the same firm at the same price; neither may be dropped.
    page = toc("2026/1000019", "2026/1000019")
    for i in (1, 2):
        page.notice(i, "2026/1000019", "İŞ", "İDARE", _lot("2026/1000019", "2.000.000,00 TRY"))
    (a,) = awards_from_reads([read(page)])
    assert a.lot_count == 2
    assert a.contract_try == 4_000_000.0


def test_a_notice_that_does_not_add_up_is_rejected_not_guessed() -> None:
    page = toc("2026/1000011")
    page.notice(1, "2026/1000011", "İŞ", "İDARE", standard_rows("2026/1000011"))
    # Drop one ':' so the value cells no longer match the labels.
    colons = [w for w in page.words if w.text == ":"]
    words = [w for w in page.words if w is not colons[4]]
    r = read(page, words)
    assert not r.notices
    assert len(r.rejected) == 1
    assert not r.complete


def test_a_shifted_value_fails_the_type_check() -> None:
    shifted = ("field", "b) Bedeli", "Uygulanmamıştır")
    rows = _replace(standard_rows("2026/1000012"), "b) Bedeli", shifted)
    page = toc("2026/1000012")
    page.notice(1, "2026/1000012", "İŞ", "İDARE", rows)
    r = read(page)
    assert not r.notices
    assert "Bedeli" in r.rejected[0].reason


@pytest.mark.parametrize("withheld", [
    "- TRY",
    ["İhalenin ilgili mevzuat gereğince yaklaşık maliyeti", "bulunmamaktadır."],
])
def test_an_estimate_printed_as_absent_is_missing_not_rejected(withheld: object) -> None:
    # Both forms are in the works bulletin of 12 November 2026: the notice says there
    # is no estimate, so it is read, and the estimate (and the discount) stay empty.
    rows = standard_rows("2026/1000020", estimate=withheld)
    page = toc("2026/1000020")
    page.notice(1, "2026/1000020", "İŞ", "İDARE", rows)
    r = read(page)
    assert r.complete, r.to_dict()
    (a,) = awards_from_reads([r])
    assert a.estimate_try is None
    assert a.discount_pct is None
    assert a.contract_try == 800_000.0


def test_a_dash_is_not_accepted_as_a_contract_price() -> None:
    rows = _replace(standard_rows("2026/1000021"), "b) Bedeli", ("field", "b) Bedeli", "- TRY"))
    page = toc("2026/1000021")
    page.notice(1, "2026/1000021", "İŞ", "İDARE", rows)
    assert not read(page).notices


def test_an_estimate_in_lira_beside_its_foreign_original() -> None:
    rows = standard_rows("2026/1000023", estimate="196.199.505,60 TRY (3.664.000,00 EUR)",
                         contract="150.000.000,00 TRY")
    page = toc("2026/1000023")
    page.notice(1, "2026/1000023", "İŞ", "İDARE", rows)
    r = read(page)
    assert r.complete, r.to_dict()
    (a,) = awards_from_reads([r])
    assert a.estimate_try == 196_199_505.60  # the lira figure, not the euro one


@pytest.mark.parametrize("price", ["532.500,00 EUR", "3.750,00 USD"])
def test_a_contract_in_another_currency_is_not_counted_as_lira(price: str) -> None:
    # Nine goods notices of 12-13 November 2026 price the contract in EUR or USD
    # against a lira estimate. No exchange rate is guessed: the lira price is empty.
    rows = standard_rows("2026/1000024", contract=price)
    page = toc("2026/1000024")
    page.notice(1, "2026/1000024", "İŞ", "İDARE", rows)
    r = read(page)
    assert r.complete, r.to_dict()
    (a,) = awards_from_reads([r])
    assert a.contract_try is None
    assert a.discount_pct is None
    assert a.winner == "Örnek Yapı Limited Şirketi"
    assert not a.cancelled


def test_an_ikn_with_a_numbered_suffix_is_kept_as_printed() -> None:
    page = toc("2026/1000025-4")
    page.notice(1, "2026/1000025-4", "İŞ", "İDARE", standard_rows("2026/1000025-4"))
    r = read(page)
    assert r.complete, r.to_dict()
    assert [n.ikn for n in r.notices] == ["2026/1000025-4"]


def test_the_table_of_contents_catches_a_missing_notice() -> None:
    page = toc("2026/1000013", "2026/1000014")
    page.notice(1, "2026/1000013", "İŞ", "İDARE", standard_rows("2026/1000013"))
    r = read(page)
    assert r.missing == ["2026/1000014"]
    assert not r.complete


def test_title_and_authority_when_line_breaks_differ() -> None:
    # The two copies of a long title wrap at different points, splitting a code.
    page = toc("2026/1000015")
    page.notice(1, "2026/1000015", "", "", standard_rows("2026/1000015"), header=[
        "UZUN BİR İŞ ADI 1978-ABC-",
        "KRS-017 VE DEVAMI",
        "UZUN BİR İŞ ADI 1978-ABC-KRS-",
        "017 VE DEVAMI ÖRNEK KOMUTANLIĞI",
    ])
    r = read(page)
    assert r.complete, r.to_dict()
    n = r.notices[0]
    assert n.title == "UZUN BİR İŞ ADI 1978-ABC-KRS-017 VE DEVAMI"
    assert n.authority == "ÖRNEK KOMUTANLIĞI"


def test_lots_unverified_survives_a_round_trip() -> None:
    a = Award(ikn="2026/1", estimate_try=10.0, contract_try=5.0, lots_unverified=True)
    back = Award.from_dict(json.loads(json.dumps(a.to_dict())))
    assert back.lots_unverified
    assert back.discount_pct is None
    # Records written before the field existed still load, and keep their discount.
    old = Award.from_dict({"ikn": "2026/2", "estimate_try": 10.0, "contract_try": 5.0})
    assert old.discount_pct == 50.0


def test_ingest_bulletin_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    good = toc("2026/1000016")
    good.notice(1, "2026/1000016", "İŞ", "İDARE", standard_rows("2026/1000016"))
    reads = {"a.zip": read_words(good.words, source="A_SONUC.pdf")}
    bad = toc("2026/1000017", "2026/1000018")
    bad.notice(1, "2026/1000017", "İŞ", "İDARE", standard_rows("2026/1000017"))
    reads["b.zip"] = read_words(bad.words, source="B_SONUC.pdf")

    def fake(path: Path) -> list[BulletinRead]:
        return [reads[Path(path).name]]

    monkeypatch.setattr(bulletin, "read_bulletin", fake)
    folder = tmp_path / "bulletins"
    folder.mkdir()
    (folder / "a.zip").write_bytes(b"PK")
    out = tmp_path / "awards.jsonl"
    runner = CliRunner()

    ok = runner.invoke(app, ["ingest-bulletin", str(folder), "-o", str(out)])
    assert ok.exit_code == 0, ok.output
    assert len(out.read_text(encoding="utf-8").splitlines()) == 1

    (folder / "b.zip").write_bytes(b"PK")
    res = runner.invoke(app, ["ingest-bulletin", str(folder), "-o", str(out), "--json"])
    assert res.exit_code == 1  # one file's contents list does not match
    report = json.loads(res.output)
    assert [f["complete"] for f in report["files"]] == [True, False]
    assert report["awards"] == 2

    # A ZIP and the PDF unpacked from it beside it are one file: listed once.
    (folder / "A_SONUC.pdf").write_bytes(b"%PDF")
    reads["A_SONUC.pdf"] = reads["a.zip"]
    res = runner.invoke(app, ["ingest-bulletin", str(folder), "-o", str(out), "--json"])
    report = json.loads(res.output)
    assert [f["source"] for f in report["files"]] == ["A_SONUC.pdf", "B_SONUC.pdf"]
    assert report["awards"] == 2


def test_a_bulletin_is_read_once_and_again_only_when_something_changed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A day's goods bulletin takes over a minute to read, and a dataset is rebuilt
    # from every file collected so far: without the saved read a daily run would
    # grow slower every day.
    page = toc("2026/1000016", "2026/1000017")
    page.notice(1, "2026/1000016", "İŞ", "İDARE", standard_rows("2026/1000016"))
    shifted = _replace(standard_rows("2026/1000017"), "b) Bedeli",
                       ("field", "b) Bedeli", "Uygulanmamıştır"))
    page.notice(2, "2026/1000017", "İŞ", "İDARE", shifted)  # rejected
    calls: list[str] = []

    def fake(path: Path) -> list[BulletinRead]:
        calls.append(Path(path).name)
        return [read_words(page.words, source="A_SONUC.pdf")]

    monkeypatch.setattr(bulletin, "read_bulletin", fake)
    f = tmp_path / "a.zip"
    f.write_bytes(b"PK one")
    first = bulletin.read_bulletin_saved(f)
    assert first[0].notices and first[0].rejected  # both kinds survive the save
    assert bulletin.read_bulletin_saved(f) == first
    assert calls == ["a.zip"]

    f.write_bytes(b"PK two")  # a different file under the same name
    assert bulletin.read_bulletin_saved(f) == first
    assert len(calls) == 2

    monkeypatch.setattr(bulletin, "_reader_key", lambda: "a newer reader")
    bulletin.read_bulletin_saved(f)
    assert len(calls) == 3

    (tmp_path / bulletin.SAVED_READS_DIR / "a.zip.json").write_text("{cut", encoding="utf-8")
    assert bulletin.read_bulletin_saved(f) == first  # unreadable: read again
    assert len(calls) == 4


def test_cli_missing_extra_names_the_right_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The terminal reads "[bulletin]" as a style tag unless it is escaped, and the
    # advice became `pip install "ihalent"`: the step the reader already took.
    def fake(path: Path) -> list[BulletinRead]:
        raise bulletin.MissingExtra(
            'Reading bulletin PDFs needs the optional extra: pip install "ihalent[bulletin]"'
        )

    monkeypatch.setattr(bulletin, "read_bulletin", fake)
    (tmp_path / "a.zip").write_bytes(b"PK")
    res = CliRunner().invoke(app, ["ingest-bulletin", str(tmp_path / "a.zip")])
    assert res.exit_code == 2
    assert '"ihalent[bulletin]"' in res.output
