"""Ingest awards from ihale-mcp / EKAP output.

This is the seam between collection and analysis, and it is a pure function of
its input — no network, no signing keys, nothing to break when EKAP rotates a
header. You collect result notices however you like (the ihale-mcp server is
the easy path; its `get_tender_announcements` returns exactly the shape this
module reads), hand the JSON to `ingest_*`, and get Award records back.

Keeping collection out of the core is deliberate. saidsurucu's ihale-mcp
already solved authenticated EKAP access well; re-implementing it here would
duplicate a fragile thing and couple this project's fate to a header format.
ihalent's job is the layer above: structure, firm-level rollups, discount and
competition analytics — the part that does not exist yet.
"""

from __future__ import annotations

from typing import Any

from ihalent.model import TENDER_TYPE_BY_CODE, Award, TenderType
from ihalent.parse import NotAResultNotice, parse_result_notice

# ihale-mcp / EKAP announcement type code for "Sonuç İlanı".
RESULT_NOTICE_CODE = "4"


def find_result_notice(announcements: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Pick the result notice out of a tender's announcement list. Returns the
    announcement dict (with its markdown_content), or None if the tender has no
    result notice yet — which is the normal state of an open tender, not an
    error."""
    notices = find_result_notices(announcements)
    return notices[0] if notices else None


def find_result_notices(announcements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every result notice in the list. A tender awarded in parts (kısmi teklif)
    publishes one result notice per lot; taking only the first would compare a
    single lot's contract against the whole tender's estimate and invent a wild
    discount. So we return them all and let award_from_announcements merge."""
    out: list[dict[str, Any]] = []
    for ann in announcements:
        type_info = ann.get("type") or {}
        code = str(type_info.get("code", ""))
        desc = str(type_info.get("description", ""))
        is_result = code == RESULT_NOTICE_CODE or "sonuç" in desc.lower()
        if is_result and ann.get("markdown_content"):
            out.append(ann)
    return out


def _tender_context(tender: dict[str, Any] | None) -> dict[str, Any]:
    """Extract (title, authority, province, tender_type) from an ihale-mcp
    search record, tolerating both the flat and nested shapes it emits."""
    if not tender:
        return {}
    type_info = tender.get("type") or {}
    code = type_info.get("code")
    tender_type = TenderType.UNKNOWN
    if code is not None:
        try:
            tender_type = TENDER_TYPE_BY_CODE.get(int(code), TenderType.UNKNOWN)
        except (TypeError, ValueError):
            tender_type = TenderType.UNKNOWN
    return {
        "title": tender.get("name") or tender.get("title"),
        "authority": tender.get("authority"),
        "province": tender.get("province"),
        "tender_type": tender_type,
    }


def award_from_announcements(
    announcements: list[dict[str, Any]], *, tender: dict[str, Any] | None = None
) -> Award | None:
    """Turn one tender's announcement list into an Award, or None if it carries
    no result notice. A multi-lot tender's per-lot notices are merged into one
    award (see _merge_lots). Context (title/authority/province/type) comes from
    the optional `tender` search record, which EKAP keeps separate from the
    notice body."""
    notices = find_result_notices(announcements)
    if not notices:
        return None
    ctx = _tender_context(tender)
    lots = [
        parse_result_notice(
            str(n["markdown_content"]),
            title=ctx.get("title"),
            authority=ctx.get("authority"),
            province=ctx.get("province"),
            tender_type=ctx.get("tender_type", TenderType.UNKNOWN),
        )
        for n in notices
    ]
    if len(lots) == 1:
        return lots[0]
    return _merge_lots(lots)


def _merge_lots(lots: list[Award]) -> Award:
    """Combine the per-lot result notices of one İKN into a single award.

    Contract prices are per-lot and sum. The estimate needs care: EKAP prints
    the tender-wide Yaklaşık Maliyet on every lot's notice, so identical
    estimates are counted once; genuinely per-lot estimates (all different) are
    summed. Bid counts are per-lot and don't aggregate to a meaningful
    tender-level number, so they are left unknown rather than misleadingly
    summed. lot_count records how many parts were merged."""
    first = lots[0]
    contracts = [a.contract_try for a in lots if a.contract_try is not None]
    contract_total = round(sum(contracts), 2) if contracts else None

    estimates = [a.estimate_try for a in lots if a.estimate_try is not None]
    if not estimates:
        estimate = None
    elif all(abs(e - estimates[0]) < 0.01 for e in estimates):
        estimate = estimates[0]  # one tender-wide estimate repeated per lot
    else:
        estimate = round(sum(estimates), 2)  # genuinely per-lot estimates

    winners_all: list[str] = []
    for a in lots:
        for w in a.winners_all or ([a.winner] if a.winner else []):
            if w not in winners_all:
                winners_all.append(w)

    return Award(
        ikn=first.ikn,
        title=first.title,
        authority=first.authority,
        province=first.province,
        tender_type=first.tender_type,
        estimate_try=estimate,
        contract_try=contract_total,
        winner=winners_all[0] if winners_all else None,
        winners_all=winners_all,
        is_joint_venture=any(a.is_joint_venture for a in lots),
        downloaders=None,
        bid_count=None,
        valid_bid_count=None,  # per-lot; not meaningful summed to tender level
        result_date=first.result_date,
        cancelled=False,
        lot_count=len(lots),
    )


def ingest_bundle(data: Any) -> list[Award]:
    """Turn a collected bundle into awards, skipping tenders without a result
    notice. Accepts three shapes, so whatever you saved from ihale-mcp usually
    just works:

    * a single `get_tender_announcements` object: ``{"announcements": [...]}``
    * a list of those objects
    * a list of ``{"tender": {...}, "announcements": [...]}`` pairs, which lets
      you attach the search record's context to each notice.
    """
    items = data if isinstance(data, list) else [data]
    awards: list[Award] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        tender = item.get("tender")
        announcements = item.get("announcements")
        if not isinstance(announcements, list):
            continue
        try:
            award = award_from_announcements(announcements, tender=tender)
        except NotAResultNotice:
            continue
        if award is not None:
            awards.append(award)
    return awards
