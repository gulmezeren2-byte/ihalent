"""Analytics tests, built on a small hand-made dataset with known answers."""

from __future__ import annotations

import pytest

from ihalent.analytics import (
    by_group,
    competition_stats,
    concentration,
    discount_stats,
    firm_profile,
    overview,
    slice_awards,
)
from ihalent.model import Award, TenderType


def award(**kw) -> Award:  # type: ignore[no-untyped-def]
    base = {"ikn": "2025/1", "tender_type": TenderType.WORKS}
    base.update(kw)
    return Award(**base)  # type: ignore[arg-type]


@pytest.fixture()
def dataset() -> list[Award]:
    return [
        award(ikn="2025/1", authority="A", province="Ankara",
              estimate_try=1000.0, contract_try=800.0, valid_bid_count=5,
              winner="ACME İNŞAAT LTD ŞTİ", winners_all=["ACME İNŞAAT LTD ŞTİ"]),
        award(ikn="2025/2", authority="A", province="Ankara",
              estimate_try=2000.0, contract_try=1000.0, valid_bid_count=1,
              winner="ACME İNŞAAT", winners_all=["ACME İNŞAAT"]),
        award(ikn="2025/3", authority="B", province="İzmir",
              estimate_try=5000.0, contract_try=4500.0, valid_bid_count=8,
              winner="BETA YAPI", winners_all=["BETA YAPI", "GAMMA"], is_joint_venture=True),
        # missing estimate -> excluded from discount, still counts as an award
        award(ikn="2025/4", authority="B", province="İzmir",
              estimate_try=None, contract_try=900.0, valid_bid_count=3,
              winner="BETA YAPI", winners_all=["BETA YAPI"]),
        # cancelled -> excluded everywhere
        award(ikn="2025/5", authority="A", cancelled=True),
    ]


def test_overview_counts(dataset: list[Award]) -> None:
    ov = overview(dataset)
    assert ov.total == 5
    assert ov.cancelled == 1
    assert ov.awarded == 4
    assert ov.missing_estimate == 1


def test_discount_excludes_missing_and_reports_it(dataset: list[Award]) -> None:
    stats = discount_stats([a for a in dataset if not a.cancelled])
    # discounts: 20%, 50%, 10% -> the missing-estimate award is excluded
    assert stats.coverage.considered == 4
    assert stats.coverage.used == 3
    assert stats.coverage.excluded == 1
    assert stats.mean == pytest.approx(26.67, abs=0.01)
    assert stats.median == 20.0
    assert stats.min == 10.0
    assert stats.max == 50.0


def test_firm_profile_folds_spelling_variants(dataset: list[Award]) -> None:
    p = firm_profile(dataset, "ACME İNŞAAT")
    assert p is not None
    assert p.wins == 2  # both ACME spellings
    assert p.total_contract_try == 1800.0
    assert p.discount.mean == 35.0  # (20 + 50) / 2


def test_firm_profile_counts_jv_membership(dataset: list[Award]) -> None:
    p = firm_profile(dataset, "GAMMA")
    assert p is not None
    assert p.wins == 1  # GAMMA only appears as a JV member on 2025/3
    assert p.joint_ventures == 1


def test_firm_profile_unknown_returns_none(dataset: list[Award]) -> None:
    assert firm_profile(dataset, "NONEXISTENT CORP") is None


def test_competition_single_bid_share(dataset: list[Award]) -> None:
    comp = competition_stats([a for a in dataset if not a.cancelled])
    # valid bids: 5, 1, 8, 3 -> one of four is a single bid
    assert comp.coverage.used == 4
    assert comp.single_bid_share == 0.25
    assert comp.median_bids == 4.0


def test_by_group_authority_sorted_desc(dataset: list[Award]) -> None:
    groups = by_group(dataset, "authority")
    labels = [g.label for g in groups]
    assert set(labels) == {"A", "B"}
    # A's mean (20,50 -> 35) beats B's (10 -> 10), so A comes first
    assert labels[0] == "A"


def test_by_group_rejects_bad_key(dataset: list[Award]) -> None:
    with pytest.raises(ValueError, match="group key"):
        by_group(dataset, "winner")


def test_empty_dataset_is_honest() -> None:
    ov = overview([])
    assert ov.awarded == 0
    assert ov.discount.mean is None
    assert ov.discount.coverage.used == 0


# -- concentration ----------------------------------------------------------


def test_concentration_hhi_and_distinct_firms(dataset: list[Award]) -> None:
    conc = concentration(dataset)
    # 4 awarded, 2 firms (ACME x2, BETA x2) -> shares 0.5/0.5 -> HHI 0.5
    assert conc.coverage.considered == 4  # the cancelled award is excluded
    assert conc.coverage.used == 4
    assert conc.distinct_firms == 2
    assert conc.hhi == 0.5


def test_concentration_folds_spelling_variants(dataset: list[Award]) -> None:
    conc = concentration(dataset)
    acme = next(f for f in conc.top if "ACME" in f.name.upper())
    assert acme.wins == 2  # two ACME spellings counted as one firm
    assert acme.contract_try == 1800.0


def test_concentration_top_sorted_ties_broken_by_value(dataset: list[Award]) -> None:
    conc = concentration(dataset)
    # both firms have 2 wins; BETA's summed value (5400) beats ACME's (1800)
    assert conc.top[0].wins == 2
    assert "BETA" in conc.top[0].name.upper()
    assert conc.top[0].win_share == 0.5


def test_concentration_single_firm_is_total(dataset: list[Award]) -> None:
    solo = [award(ikn="x", winner="ONLY CO", winners_all=["ONLY CO"], contract_try=100.0)]
    conc = concentration(solo)
    assert conc.hhi == 1.0
    assert conc.distinct_firms == 1


def test_concentration_without_a_winner_is_covered_not_counted() -> None:
    conc = concentration([award(ikn="x", winner=None, winners_all=[])])
    assert conc.coverage.considered == 1
    assert conc.coverage.used == 0
    assert conc.hhi is None


def test_concentration_empty_is_honest() -> None:
    conc = concentration([])
    assert conc.hhi is None
    assert conc.distinct_firms == 0
    assert conc.coverage.used == 0


# -- slice_awards -----------------------------------------------------------


def test_slice_by_authority(dataset: list[Award]) -> None:
    subset, label = slice_awards(dataset, authority="A")
    assert {a.ikn for a in subset} == {"2025/1", "2025/2", "2025/5"}
    assert label == "authority ~ 'A'"


def test_slice_authority_is_case_insensitive_substring(dataset: list[Award]) -> None:
    subset, _ = slice_awards(dataset, authority="b")
    assert {a.ikn for a in subset} == {"2025/3", "2025/4"}


def test_slice_by_province(dataset: list[Award]) -> None:
    subset, label = slice_awards(dataset, province="İzmir")
    assert {a.ikn for a in subset} == {"2025/3", "2025/4"}
    assert "province" in label


def test_slice_no_filter_returns_all(dataset: list[Award]) -> None:
    subset, label = slice_awards(dataset)
    assert len(subset) == len(dataset)
    assert label == "all awards"


def test_concentration_within_one_authority(dataset: list[Award]) -> None:
    subset, label = slice_awards(dataset, authority="A")
    conc = concentration(subset, label=label)
    # authority A: two ACME wins (the cancelled one drops out) -> one firm, HHI 1
    assert conc.coverage.considered == 2
    assert conc.distinct_firms == 1
    assert conc.hhi == 1.0
