"""MCP tool-logic tests. These exercise the plain functions, not the transport,
so they run without the `mcp` extra installed."""

from __future__ import annotations

from pathlib import Path

import pytest

from ihalent.mcp_server import (
    tool_concentration,
    tool_discounts,
    tool_firm,
    tool_flags,
    tool_ingest_bundle,
    tool_overview,
    tool_parse_notice,
)
from ihalent.model import Award, TenderType
from ihalent.store import dump_awards


@pytest.fixture()
def dataset_path(tmp_path: Path) -> str:
    awards = [
        Award(ikn="2025/1", authority="A", winner="ACME LTD", winners_all=["ACME LTD"],
              estimate_try=1000.0, contract_try=800.0, valid_bid_count=4,
              tender_type=TenderType.WORKS),
        Award(ikn="2025/2", authority="B", winner="BETA AŞ", winners_all=["BETA AŞ"],
              estimate_try=2000.0, contract_try=1900.0, valid_bid_count=1,
              tender_type=TenderType.SERVICE),
    ]
    path = tmp_path / "awards.jsonl"
    dump_awards(awards, path)
    return str(path)


def test_overview(dataset_path: str) -> None:
    result = tool_overview(dataset_path)
    assert result["awarded"] == 2
    assert result["discount"]["min"] == 5.0  # BETA: (2000-1900)/2000


def test_firm_found(dataset_path: str) -> None:
    result = tool_firm("ACME", dataset_path)
    assert result["found"] is True
    assert result["wins"] == 1


def test_firm_not_found(dataset_path: str) -> None:
    result = tool_firm("NOBODY", dataset_path)
    assert result["found"] is False


def test_discounts(dataset_path: str) -> None:
    result = tool_discounts("authority", dataset_path)
    assert {g["label"] for g in result["groups"]} == {"A", "B"}


def test_concentration(dataset_path: str) -> None:
    result = tool_concentration(awards_path=dataset_path)
    # two firms, one win each -> shares 0.5/0.5 -> HHI 0.5
    assert result["distinct_firms"] == 2
    assert result["hhi"] == 0.5
    assert result["coverage"]["used"] == 2


def test_concentration_by_authority(dataset_path: str) -> None:
    result = tool_concentration(authority="A", awards_path=dataset_path)
    assert result["label"] == "authority ~ 'A'"
    assert result["distinct_firms"] == 1  # only ACME sits in authority A
    assert result["hhi"] == 1.0


def test_flags(dataset_path: str) -> None:
    result = tool_flags(awards_path=dataset_path)
    # BETA (2025/2) has a single valid bid; ACME (2025/1) is clean
    assert result["counts"]["single_bid"] == 1
    assert result["flagged_count"] == 1
    assert result["flagged"][0]["ikn"] == "2025/2"


def test_parse_notice() -> None:
    md = (
        "**SONUÇ İLANI** 2025/1234567\n"
        "| Yaklaşık Maliyeti | : | 1.000.000,00 TRY |\n"
        "| Bedeli | : | 700.000,00 TRY |\n"
        "| Yüklenicisi | : | X LTD |\n"
    )
    result = tool_parse_notice(md)
    assert result["discount_pct"] == 30.0


def test_parse_notice_rejects_non_notice() -> None:
    result = tool_parse_notice("just some text")
    assert "error" in result


def test_ingest_appends_to_dataset(dataset_path: str) -> None:
    bundle = {
        "announcements": [
            {
                "type": {"code": "4", "description": "Sonuç İlanı"},
                "markdown_content": (
                    "**SONUÇ İLANI** 2025/9999999\n"
                    "| Yaklaşık Maliyeti | : | 500,00 TRY |\n"
                    "| Bedeli | : | 400,00 TRY |\n"
                    "| Yüklenicisi | : | NEW LTD |\n"
                ),
            }
        ]
    }
    result = tool_ingest_bundle(bundle, dataset_path)
    assert result["new_in_bundle"] == 1
    assert result["written"] == 3  # 2 existing + 1 new


def test_no_dataset_is_a_clear_error() -> None:
    with pytest.raises(ValueError, match="No awards dataset"):
        tool_overview(None)
