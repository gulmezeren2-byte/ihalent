"""Analytics over a set of awards.

Three questions this layer answers, and one rule it never breaks.

The questions:
  * Firm history — what has one company won, for how much, at what discount?
  * Discount distribution — how far below estimate do contracts land, sliced
    by authority, province or tender type?
  * Competition — how many bidders show up, and how often does exactly one?

The rule: every statistic reports the ground it stands on. A mean discount is
meaningless without "over how many awards, and how many were dropped for a
missing estimate." So each result carries an `Coverage` — total considered,
used, and excluded — and the renderer always prints it. This is the same
honesty discipline as the andon project: a number without its denominator is
an opinion.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from statistics import median

from ihalent.model import Award, TenderType
from ihalent.normalize import display_name, normalize_company


@dataclass
class Coverage:
    considered: int
    used: int

    @property
    def excluded(self) -> int:
        return self.considered - self.used

    def to_dict(self) -> dict[str, int]:
        return {"considered": self.considered, "used": self.used, "excluded": self.excluded}


def _discounts(awards: Iterable[Award]) -> tuple[list[float], Coverage]:
    considered = 0
    values: list[float] = []
    for a in awards:
        if a.cancelled:
            continue
        considered += 1
        d = a.discount_pct
        if d is not None:
            values.append(d)
    return values, Coverage(considered=considered, used=len(values))


@dataclass
class DiscountStats:
    label: str
    coverage: Coverage
    mean: float | None = None
    median: float | None = None
    min: float | None = None
    max: float | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "label": self.label,
            "coverage": self.coverage.to_dict(),
            "mean": self.mean,
            "median": self.median,
            "min": self.min,
            "max": self.max,
        }


def discount_stats(awards: Iterable[Award], label: str = "all awards") -> DiscountStats:
    values, coverage = _discounts(awards)
    if not values:
        return DiscountStats(label=label, coverage=coverage)
    return DiscountStats(
        label=label,
        coverage=coverage,
        mean=round(sum(values) / len(values), 2),
        median=round(median(values), 2),
        min=round(min(values), 2),
        max=round(max(values), 2),
    )


@dataclass
class FirmProfile:
    key: str
    name: str
    wins: int
    total_contract_try: float
    known_contract_count: int  # wins whose contract value was published
    discount: DiscountStats
    joint_ventures: int
    distinct_spellings: int  # how many normalized company keys the query matched
    authorities: dict[str, int] = field(default_factory=dict)
    provinces: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "name": self.name,
            "wins": self.wins,
            "total_contract_try": round(self.total_contract_try, 2),
            "known_contract_count": self.known_contract_count,
            "discount": self.discount.to_dict(),
            "joint_ventures": self.joint_ventures,
            "distinct_spellings": self.distinct_spellings,
            "top_authorities": dict(
                sorted(self.authorities.items(), key=lambda kv: -kv[1])[:5]
            ),
            "provinces": dict(sorted(self.provinces.items(), key=lambda kv: -kv[1])),
        }


def firm_profile(awards: Sequence[Award], query: str, *, exact: bool = False) -> FirmProfile | None:
    """Everything one firm won across the dataset.

    `query` is normalized and matched against each winner's normalized key.
    By default the match is a substring ("acme" finds "acme insaat ltd"), which
    is what a human searching a name wants; pass exact=True to require the whole
    key to match. Either way, `distinct_spellings` reports how many different
    company keys were folded in, so an over-broad query is visible rather than
    silently merging unrelated firms."""
    key = normalize_company(query)
    if not key:
        return None
    matched: list[Award] = []
    raw_names: list[str] = []
    matched_keys: set[str] = set()
    for a in awards:
        if a.cancelled:
            continue
        for member in a.winners_all or ([a.winner] if a.winner else []):
            member_key = normalize_company(member)
            hit = member_key == key if exact else key in member_key
            if hit:
                matched.append(a)
                raw_names.append(member)
                matched_keys.add(member_key)
                break
    if not matched:
        return None

    total = sum(a.contract_try for a in matched if a.contract_try is not None)
    known = sum(1 for a in matched if a.contract_try is not None)
    authorities: dict[str, int] = {}
    provinces: dict[str, int] = {}
    for a in matched:
        if a.authority:
            authorities[a.authority] = authorities.get(a.authority, 0) + 1
        if a.province:
            provinces[a.province] = provinces.get(a.province, 0) + 1

    return FirmProfile(
        key=key,
        name=display_name(raw_names),
        wins=len(matched),
        total_contract_try=total,
        known_contract_count=known,
        discount=discount_stats(matched, label=display_name(raw_names)),
        joint_ventures=sum(1 for a in matched if a.is_joint_venture),
        distinct_spellings=len(matched_keys),
        authorities=authorities,
        provinces=provinces,
    )


@dataclass
class CompetitionStats:
    coverage: Coverage
    mean_bids: float | None = None
    median_bids: float | None = None
    single_bid_share: float | None = None  # fraction of awards with <=1 valid bid

    def to_dict(self) -> dict[str, object]:
        return {
            "coverage": self.coverage.to_dict(),
            "mean_bids": self.mean_bids,
            "median_bids": self.median_bids,
            "single_bid_share": self.single_bid_share,
        }


def competition_stats(awards: Iterable[Award]) -> CompetitionStats:
    considered = 0
    counts: list[int] = []
    singles = 0
    for a in awards:
        if a.cancelled:
            continue
        considered += 1
        if a.valid_bid_count is not None:
            counts.append(a.valid_bid_count)
            if a.valid_bid_count <= 1:
                singles += 1
    coverage = Coverage(considered=considered, used=len(counts))
    if not counts:
        return CompetitionStats(coverage=coverage)
    return CompetitionStats(
        coverage=coverage,
        mean_bids=round(sum(counts) / len(counts), 2),
        median_bids=round(median(counts), 2),
        single_bid_share=round(singles / len(counts), 3),
    )


@dataclass
class FirmShare:
    key: str
    name: str
    wins: int
    contract_try: float  # summed known contract value across those wins
    win_share: float  # wins / total attributed wins (0..1)

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "name": self.name,
            "wins": self.wins,
            "contract_try": round(self.contract_try, 2),
            "win_share": round(self.win_share, 4),
        }


@dataclass
class Concentration:
    label: str
    coverage: Coverage
    distinct_firms: int
    hhi: float | None = None  # 0..1 over win counts; None if nothing usable
    top: list[FirmShare] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "label": self.label,
            "coverage": self.coverage.to_dict(),
            "distinct_firms": self.distinct_firms,
            "hhi": self.hhi,
            "top": [f.to_dict() for f in self.top],
        }


def _lead_winner(a: Award) -> str | None:
    return a.winner or (a.winners_all[0] if a.winners_all else None)


def concentration(
    awards: Iterable[Award], label: str = "all awards", *, top: int = 5
) -> Concentration:
    """How concentrated are the winners over a set of awards?

    Each award is attributed to its lead winner, spelling variants are folded
    (so "ACME İNŞAAT" and "Acme Insaat Ltd." are one firm), and the result
    reports the Herfindahl-Hirschman Index over win counts plus the leading
    firms. Where single-bid share measures competition *within* one tender, this
    measures it *across* tenders: are the same few firms winning everything?

    HHI is the sum of squared win shares, in [0, 1]: ~1 means one firm takes
    almost everything, 1/n means n firms share evenly. As a rough guide — the US
    DOJ/FTC thresholds rescaled to 0-1 — below 0.15 is unconcentrated, 0.15-0.25
    moderate, above 0.25 highly concentrated. It is a reason to look closer, not
    a verdict: a small authority with few tenders is concentrated by arithmetic,
    which is exactly why the coverage travels with the number."""
    considered = 0
    wins: dict[str, int] = {}
    value: dict[str, float] = {}
    names: dict[str, list[str]] = {}
    for a in awards:
        if a.cancelled:
            continue
        considered += 1
        lead = _lead_winner(a)
        key = normalize_company(lead) if lead else ""
        if not key:
            continue
        wins[key] = wins.get(key, 0) + 1
        if a.contract_try is not None:
            value[key] = value.get(key, 0.0) + a.contract_try
        names.setdefault(key, []).append(lead)  # type: ignore[arg-type]

    used = sum(wins.values())
    coverage = Coverage(considered=considered, used=used)
    if used == 0:
        return Concentration(label=label, coverage=coverage, distinct_firms=0)

    hhi = round(sum((n / used) ** 2 for n in wins.values()), 4)
    shares = [
        FirmShare(
            key=k,
            name=display_name(names[k]),
            wins=n,
            contract_try=value.get(k, 0.0),
            win_share=n / used,
        )
        for k, n in wins.items()
    ]
    shares.sort(key=lambda s: (-s.wins, -s.contract_try, s.key))
    return Concentration(
        label=label,
        coverage=coverage,
        distinct_firms=len(wins),
        hhi=hhi,
        top=shares[:top],
    )


def slice_awards(
    awards: Sequence[Award], *, authority: str | None = None, province: str | None = None
) -> tuple[list[Award], str]:
    """Narrow a dataset by authority/province (case-insensitive substring) and
    return the subset together with a label describing the slice. Shared by the
    CLI and the MCP server so concentration means the same thing in both."""
    subset = list(awards)
    parts: list[str] = []
    if authority:
        needle = authority.casefold()
        subset = [a for a in subset if a.authority and needle in a.authority.casefold()]
        parts.append(f"authority ~ {authority!r}")
    if province:
        needle = province.casefold()
        subset = [a for a in subset if a.province and needle in a.province.casefold()]
        parts.append(f"province ~ {province!r}")
    return subset, "; ".join(parts) if parts else "all awards"


# Procurement red-flag names. Stable strings, so a JSON consumer can key on them.
FLAG_SINGLE_BID = "single_bid"  # one valid bid: no competing offer
FLAG_LOW_DISCOUNT = "low_discount"  # contract landed at/near the public estimate
FLAG_NO_ESTIMATE = "no_estimate"  # no published estimate: the award can't be audited
FLAG_HIGH_DROPOUT = "high_dropout"  # many took the documents, almost none bid validly
FLAG_ORDER = [FLAG_SINGLE_BID, FLAG_LOW_DISCOUNT, FLAG_NO_ESTIMATE, FLAG_HIGH_DROPOUT]


@dataclass
class AwardFlags:
    ikn: str
    title: str | None
    authority: str | None
    winner: str | None
    contract_try: float | None
    discount_pct: float | None
    flags: list[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "ikn": self.ikn,
            "title": self.title,
            "authority": self.authority,
            "winner": self.winner,
            "contract_try": (
                round(self.contract_try, 2) if self.contract_try is not None else None
            ),
            "discount_pct": self.discount_pct,
            "flags": self.flags,
        }


@dataclass
class RiskReport:
    coverage: Coverage
    low_discount_pct: float
    counts: dict[str, int]
    flagged: list[AwardFlags] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "coverage": self.coverage.to_dict(),
            "low_discount_pct": self.low_discount_pct,
            "counts": self.counts,
            "flagged_count": len(self.flagged),
            "flagged": [f.to_dict() for f in self.flagged],
        }


def _award_flags(a: Award, low_discount_pct: float) -> list[str]:
    flags: list[str] = []
    if a.single_bid:  # True only when the valid-bid count is known and <= 1
        flags.append(FLAG_SINGLE_BID)
    if a.discount_pct is not None and a.discount_pct < low_discount_pct:
        # Includes negative discounts (contract above estimate) — an even louder
        # version of the same signal: no downward price pressure.
        flags.append(FLAG_LOW_DISCOUNT)
    if a.estimate_try is None:
        flags.append(FLAG_NO_ESTIMATE)
    if (
        a.downloaders is not None
        and a.downloaders >= 5
        and a.valid_bid_count is not None
        and a.valid_bid_count / a.downloaders < 0.2
    ):
        flags.append(FLAG_HIGH_DROPOUT)
    return flags


def risk_flags(awards: Iterable[Award], *, low_discount_pct: float = 3.0) -> RiskReport:
    """Per-award procurement red flags — the signals transparency work looks for.

    None of these is proof of anything; each is a reason to read the file. A
    single valid bid, a contract that landed on top of the public estimate, no
    published estimate at all, or a tender many firms took documents for but
    almost none bid on — these are the classic markers of weak or absent
    competition. An award can raise several at once, and the ones that raise the
    most (and involve the most money) sort to the top. The coverage says how many
    awards were examined; a flag count is only as meaningful as its denominator."""
    considered = 0
    counts: dict[str, int] = dict.fromkeys(FLAG_ORDER, 0)
    flagged: list[AwardFlags] = []
    for a in awards:
        if a.cancelled:
            continue
        considered += 1
        flags = _award_flags(a, low_discount_pct)
        if not flags:
            continue
        for f in flags:
            counts[f] += 1
        flagged.append(
            AwardFlags(
                ikn=a.ikn,
                title=a.title,
                authority=a.authority,
                winner=a.winner,
                contract_try=a.contract_try,
                discount_pct=a.discount_pct,
                flags=flags,
            )
        )
    flagged.sort(key=lambda f: (-len(f.flags), -(f.contract_try or 0.0), f.ikn))
    return RiskReport(
        coverage=Coverage(considered=considered, used=considered),
        low_discount_pct=low_discount_pct,
        counts=counts,
        flagged=flagged,
    )


def by_group(
    awards: Iterable[Award], key: str, *, min_awards: int = 1
) -> list[DiscountStats]:
    """Discount stats grouped by 'authority', 'province' or 'tender_type'.

    Groups thinner than `min_awards` are still returned but the caller can
    filter them; a mean over two awards is not a trend and the coverage says so.
    """
    getters = {
        "authority": lambda a: a.authority,
        "province": lambda a: a.province,
        "tender_type": lambda a: (
            a.tender_type.value if a.tender_type != TenderType.UNKNOWN else None
        ),
    }
    if key not in getters:
        raise ValueError(f"group key must be one of {sorted(getters)}, got {key!r}")
    get = getters[key]

    buckets: dict[str, list[Award]] = {}
    for a in awards:
        if a.cancelled:
            continue
        g = get(a)
        if g:
            buckets.setdefault(g, []).append(a)

    out = [discount_stats(v, label=k) for k, v in buckets.items() if len(v) >= min_awards]
    out.sort(key=lambda s: (s.mean if s.mean is not None else -1), reverse=True)
    return out


@dataclass
class Overview:
    total: int
    cancelled: int
    awarded: int
    discount: DiscountStats
    competition: CompetitionStats
    total_contract_try: float
    missing_estimate: int
    missing_bid_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "total": self.total,
            "cancelled": self.cancelled,
            "awarded": self.awarded,
            "discount": self.discount.to_dict(),
            "competition": self.competition.to_dict(),
            "total_contract_try": round(self.total_contract_try, 2),
            "data_gaps": {
                "missing_estimate": self.missing_estimate,
                "missing_bid_count": self.missing_bid_count,
            },
        }


def overview(awards: Sequence[Award]) -> Overview:
    awarded = [a for a in awards if not a.cancelled]
    return Overview(
        total=len(awards),
        cancelled=sum(1 for a in awards if a.cancelled),
        awarded=len(awarded),
        discount=discount_stats(awarded),
        competition=competition_stats(awarded),
        total_contract_try=sum(a.contract_try for a in awarded if a.contract_try is not None),
        missing_estimate=sum(1 for a in awarded if a.estimate_try is None),
        missing_bid_count=sum(1 for a in awarded if a.valid_bid_count is None),
    )
