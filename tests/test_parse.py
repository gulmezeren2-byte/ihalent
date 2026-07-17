import pytest

from ihalent.model import TenderType
from ihalent.parse import (
    NotAResultNotice,
    parse_money_tr,
    parse_result_notice,
    split_winners,
)


def test_money_turkish_format() -> None:
    assert parse_money_tr("2.783.270,09 TRY") == 2783270.09
    assert parse_money_tr("19.709.997,40 TL") == 19709997.40
    assert parse_money_tr("897,40") == 897.40


def test_money_missing_returns_none() -> None:
    assert parse_money_tr("bilgi yok") is None
    assert parse_money_tr("") is None


def test_parse_award_with_discount(notice_award_jv: str) -> None:
    a = parse_result_notice(notice_award_jv, tender_type=TenderType.WORKS)
    assert a.ikn == "2025/2337797"
    assert a.estimate_try == 2783270.09
    assert a.contract_try == 2227000.00
    assert a.discount_pct == 19.99
    assert a.downloaders == 8
    assert a.bid_count == 4
    assert a.valid_bid_count == 3
    assert a.single_bid is False
    assert a.is_joint_venture is True
    assert a.winner == "MUHAMMED HANEFİ YILDIRIM"
    assert a.result_date == "2026-01-26"
    assert a.cancelled is False


def test_parse_large_award(notice_award_big: str) -> None:
    a = parse_result_notice(notice_award_big)
    assert a.ikn == "2025/2198370"
    assert a.discount_pct == 33.87
    assert a.valid_bid_count == 12
    assert a.winner == "ÖZDEN YEL"
    assert len(a.winners_all) == 2


def test_parse_cancelled(notice_cancelled: str) -> None:
    a = parse_result_notice(notice_cancelled)
    assert a.ikn == "2025/2500001"
    assert a.cancelled is True
    assert a.winner is None
    assert a.contract_try is None
    # estimate is still captured even for a cancellation
    assert a.estimate_try == 1000000.00
    # a cancelled tender has no meaningful discount
    assert a.discount_pct is None


def test_non_result_notice_rejected() -> None:
    with pytest.raises(NotAResultNotice):
        parse_result_notice("**İHALE İLANI** Bir yapım işi ihale edilecektir. 2025/1 için.")


def test_missing_ikn_rejected() -> None:
    with pytest.raises(NotAResultNotice, match="İKN"):
        parse_result_notice("**SONUÇ İLANI** yüklenici bir firma sözleşmenin bedeli yok")


def test_split_winners_joint_venture() -> None:
    lead, members, jv = split_winners("A İNŞAAT LTD, B TİCARET AŞ İş Ortaklığı")
    assert lead == "A İNŞAAT LTD"
    assert members == ["A İNŞAAT LTD", "B TİCARET AŞ"]
    assert jv is True


def test_split_winners_single_firm() -> None:
    lead, members, jv = split_winners("TEK FİRMA İNŞAAT LİMİTED ŞİRKETİ")
    assert lead == "TEK FİRMA İNŞAAT LİMİTED ŞİRKETİ"
    assert members == ["TEK FİRMA İNŞAAT LİMİTED ŞİRKETİ"]
    assert jv is False


def test_discount_undefined_without_estimate() -> None:
    a = parse_result_notice(
        "**SONUÇ İLANI** 2025/1234567\n| Bedeli | : | 100.000,00 TRY |\n"
        "| Yüklenicisi | : | X LTD |",
    )
    assert a.contract_try == 100000.0
    assert a.estimate_try is None
    assert a.discount_pct is None  # never guessed
