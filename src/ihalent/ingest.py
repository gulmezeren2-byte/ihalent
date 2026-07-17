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
    for ann in announcements:
        type_info = ann.get("type") or {}
        code = str(type_info.get("code", ""))
        desc = str(type_info.get("description", ""))
        is_result = code == RESULT_NOTICE_CODE or "sonuç" in desc.lower()
        if is_result and ann.get("markdown_content"):
            return ann
    return None


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
    no result notice. Context (title/authority/province/type) is taken from the
    optional `tender` search record, which EKAP keeps separate from the notice
    body."""
    notice = find_result_notice(announcements)
    if notice is None:
        return None
    ctx = _tender_context(tender)
    return parse_result_notice(
        str(notice["markdown_content"]),
        title=ctx.get("title"),
        authority=ctx.get("authority"),
        province=ctx.get("province"),
        tender_type=ctx.get("tender_type", TenderType.UNKNOWN),
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
