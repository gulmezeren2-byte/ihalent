"""Ingest tests, using the exact JSON shapes ihale-mcp emits."""

from __future__ import annotations

from ihalent.ingest import award_from_announcements, find_result_notice, ingest_bundle
from ihalent.model import TenderType

# A trimmed but real-shaped get_tender_announcements response: a pre-notice and
# a result notice, exactly as ihale-mcp returns them.
ANNOUNCEMENTS = [
    {
        "type": {"code": "1", "description": "Ön İlan"},
        "markdown_content": "**BİNA ONARIMI** ... (pre-notice, no result)",
    },
    {
        "type": {"code": "4", "description": "Sonuç İlanı"},
        "markdown_content": (
            "**SONUÇ İLANI** \n"
            "| **İhale kayıt numarası** | **:** | **2025/2337797** |\n"
            "| **d)** Yaklaşık Maliyeti | : | 2.783.270,09 TRY |\n"
            "| **c)** Toplam Geçerli Teklif Sayısı | : | 3 |\n"
            "| **b)** Bedeli | : | 2.227.000,00 TRY |\n"
            "| **d)** Yüklenicisi | : | X İNŞAAT LTD |\n"
        ),
    },
]

TENDER = {
    "id": "abc",
    "name": "Bina Onarım İşi",
    "authority": "Ağrı İl Özel İdaresi",
    "province": "AĞRI",
    "type": {"code": "2", "description": "Yapım"},
}


def test_find_result_notice_picks_the_right_one() -> None:
    notice = find_result_notice(ANNOUNCEMENTS)
    assert notice is not None
    assert notice["type"]["code"] == "4"


def test_find_result_notice_none_when_open() -> None:
    only_prenotice = [ANNOUNCEMENTS[0]]
    assert find_result_notice(only_prenotice) is None


def test_award_from_announcements_with_context() -> None:
    award = award_from_announcements(ANNOUNCEMENTS, tender=TENDER)
    assert award is not None
    assert award.ikn == "2025/2337797"
    assert award.discount_pct == 19.99
    assert award.authority == "Ağrı İl Özel İdaresi"
    assert award.province == "AĞRI"
    assert award.tender_type is TenderType.WORKS  # code 2 -> works


def test_award_without_context_still_parses() -> None:
    award = award_from_announcements(ANNOUNCEMENTS)
    assert award is not None
    assert award.ikn == "2025/2337797"
    assert award.authority is None


def test_ingest_bundle_single_object() -> None:
    bundle = {"announcements": ANNOUNCEMENTS}
    awards = ingest_bundle(bundle)
    assert len(awards) == 1
    assert awards[0].ikn == "2025/2337797"


def test_ingest_bundle_list_of_pairs() -> None:
    bundle = [
        {"tender": TENDER, "announcements": ANNOUNCEMENTS},
        {"tender": {"name": "open tender"}, "announcements": [ANNOUNCEMENTS[0]]},
    ]
    awards = ingest_bundle(bundle)
    # the open tender (pre-notice only) is skipped, not an error
    assert len(awards) == 1
    assert awards[0].authority == "Ağrı İl Özel İdaresi"


def test_ingest_bundle_tolerates_junk() -> None:
    bundle = ["not a dict", {"no": "announcements"}, {"announcements": "not a list"}]
    assert ingest_bundle(bundle) == []
