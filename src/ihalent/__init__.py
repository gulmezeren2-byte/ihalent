"""ihalent — Turkish public-tender award intelligence.

Small public surface:

    from ihalent import Award, parse_result_notice, load_awards
    from ihalent.analytics import firm_profile, discount_stats, overview

The parse + analytics core has no network dependency. Live collection from
EKAP lives behind the `collect` extra so data-crunching pipelines stay light.
"""

from importlib.metadata import PackageNotFoundError, version

from ihalent.ingest import award_from_announcements, ingest_bundle
from ihalent.model import Award, TenderType
from ihalent.parse import NotAResultNotice, parse_result_notice
from ihalent.store import dump_awards, load_awards

try:
    # Single source of truth: the installed distribution version, so
    # `ihalent --version` can never drift from pyproject.toml.
    __version__ = version("ihalent")
except PackageNotFoundError:  # pragma: no cover - running from a source tree
    __version__ = "0.0.0+unknown"

__all__ = [
    "Award",
    "TenderType",
    "parse_result_notice",
    "NotAResultNotice",
    "ingest_bundle",
    "award_from_announcements",
    "load_awards",
    "dump_awards",
    "__version__",
]
