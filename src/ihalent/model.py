"""The data model for a tender award.

One decision governs this whole file: every field that the source announcement
might not carry is Optional, and a missing value is ``None`` — never zero,
never an empty string, never a guess. A discount rate computed from a missing
estimate is not "0%"; it is unknown, and the analytics layer is required to
treat it as such. Half the value of this tool is in refusing to invent the
numbers the government did not publish.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class TenderType(str, Enum):
    GOODS = "mal"
    WORKS = "yapim"
    SERVICE = "hizmet"
    CONSULTING = "danismanlik"
    UNKNOWN = "unknown"


# EKAP's numeric tender-type codes, as seen on the search API.
TENDER_TYPE_BY_CODE = {
    1: TenderType.GOODS,
    2: TenderType.WORKS,
    3: TenderType.SERVICE,
    4: TenderType.CONSULTING,
}


@dataclass
class Award:
    """A single awarded (or cancelled) tender, as published in its result notice.

    Money is in Turkish Lira (nominal, as printed). We deliberately do not
    inflation-adjust here — that is an analysis choice the caller makes with
    full knowledge of the date, not something the record should bake in.
    """

    ikn: str  # İhale Kayıt Numarası, e.g. "2025/2198370" — the primary key
    title: str | None = None
    authority: str | None = None
    province: str | None = None
    tender_type: TenderType = TenderType.UNKNOWN

    estimate_try: float | None = None  # Yaklaşık Maliyet
    contract_try: float | None = None  # Sözleşme Bedeli
    winner: str | None = None  # lead bidder (first named party)
    winners_all: list[str] = field(default_factory=list)  # full JV member list
    is_joint_venture: bool = False

    downloaders: int | None = None  # bought/downloaded the documents
    bid_count: int | None = None  # Toplam Teklif Sayısı
    valid_bid_count: int | None = None  # Toplam Geçerli Teklif Sayısı

    result_date: str | None = None  # contract date, ISO where known
    cancelled: bool = False
    lot_count: int = 1  # >1 when a tender was awarded in parts (kısmi teklif)

    @property
    def is_partial(self) -> bool:
        """True for a multi-lot tender (kısmi teklif) whose parts were merged
        into this record. Discounts on merged records are only as trustworthy
        as the estimate-vs-summed-contract comparison — see ingest._merge_lots."""
        return self.lot_count > 1

    @property
    def discount_pct(self) -> float | None:
        """Kırım / tenzilat: how far below the public estimate the contract
        landed, as a percent. Undefined without both numbers, and undefined
        (not infinite) if the estimate is zero."""
        if self.estimate_try is None or self.contract_try is None:
            return None
        if self.estimate_try == 0:
            return None
        return round(100.0 * (self.estimate_try - self.contract_try) / self.estimate_try, 2)

    @property
    def single_bid(self) -> bool | None:
        """One valid bid means no real competition — a flag procurement
        watchdogs care about. Unknown if the count is missing."""
        if self.valid_bid_count is None:
            return None
        return self.valid_bid_count <= 1

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["tender_type"] = self.tender_type.value
        d["discount_pct"] = self.discount_pct
        d["single_bid"] = self.single_bid
        d["is_partial"] = self.is_partial
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Award:
        raw_type = d.get("tender_type", "unknown")
        tender_type = (
            raw_type if isinstance(raw_type, TenderType) else TenderType(str(raw_type))
        )
        return cls(
            ikn=str(d["ikn"]),
            title=d.get("title"),
            authority=d.get("authority"),
            province=d.get("province"),
            tender_type=tender_type,
            estimate_try=d.get("estimate_try"),
            contract_try=d.get("contract_try"),
            winner=d.get("winner"),
            winners_all=list(d.get("winners_all") or []),
            is_joint_venture=bool(d.get("is_joint_venture", False)),
            downloaders=d.get("downloaders"),
            bid_count=d.get("bid_count"),
            valid_bid_count=d.get("valid_bid_count"),
            result_date=d.get("result_date"),
            cancelled=bool(d.get("cancelled", False)),
            lot_count=int(d.get("lot_count", 1) or 1),
        )
