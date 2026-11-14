"""Download the daily Kamu İhale Bülteni from EKAP's official bulletin page.

This is the one place ihalent touches the network, and it is kept narrow on
purpose: one public page, the files KİK publishes there for anyone to download,
one file per request, at a human pace. It never tries to get past a
verification screen. If the page ever asks a visitor to prove they are human,
or refuses the request, it stops and says so — it does not retry.

Every download is checked before it is kept: it must be a ZIP and carry the
requested date and tender type in its name, because a malformed request makes
the page quietly serve *today's* bulletin instead of the one asked for.
"""

from __future__ import annotations

import http.cookiejar
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import date, timedelta
from html.parser import HTMLParser
from pathlib import Path

from ihalent.model import TenderType

BULLETIN_PAGE = "https://ekap.kik.gov.tr/ekap/ilan/bultenindirme.aspx"
_PREFIX = "ctl00$ContentPlaceHolder1$"
_TYPE_FIELD = _PREFIX + "ddlstBxIhaleTur"
_DATE_FIELD = _PREFIX + "etBultenTarihi$EkapTakvimTextBox_etBultenTarihi"
_ARCHIVE_BUTTON = _PREFIX + "btnYukle"

# Codes and names as the page uses them.
TYPE_CODE = {
    TenderType.GOODS: "1", TenderType.WORKS: "2",
    TenderType.SERVICE: "3", TenderType.CONSULTING: "4",
}
_TODAY_BUTTON = {
    TenderType.GOODS: "lnkBtnMal", TenderType.WORKS: "lnkBtnYapim",
    TenderType.SERVICE: "lnkBtnHizmet", TenderType.CONSULTING: "lnkBtnDanismanlik",
}
FILE_TAG = {
    TenderType.GOODS: "MAL", TenderType.WORKS: "YAPIM",
    TenderType.SERVICE: "HIZMET", TenderType.CONSULTING: "DANISMANLIK",
}

# The server only offers RSA key exchange with AES-GCM, which Python's default
# cipher list leaves out. Add exactly those two suites; certificate and host
# checks stay on.
_CIPHERS = "ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:AES128-GCM-SHA256:AES256-GCM-SHA384"
_VERIFICATION = re.compile(
    r"turnstile|g-recaptcha|hcaptcha|cf-chl|challenge-platform|captcha", re.IGNORECASE
)
MIN_PAUSE_SECONDS = 2.0


class FetchError(RuntimeError):
    """The bulletin could not be downloaded."""


class AccessBlocked(FetchError):
    """The page asked for human verification or refused the request. Stop."""


class NoBulletin(FetchError):
    """The page answered, but not with the requested bulletin."""


Opener = urllib.request.OpenerDirector


@dataclass
class FetchResult:
    day: date
    path: Path
    downloaded: bool  # False when the file was already on disk


def bulletin_filename(day: date, kind: TenderType) -> str:
    """The name KİK gives the file, e.g. BULTEN_13112026_YAPIM.zip."""
    return f"BULTEN_{day:%d%m%Y}_{FILE_TAG[kind]}.zip"


def _tls_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.set_ciphers(_CIPHERS)
    return ctx


def default_opener() -> Opener:
    """A cookie-keeping opener; the page's form only works within its session."""
    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
        urllib.request.HTTPSHandler(context=_tls_context()),
    )


class _HiddenFields(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.fields: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        name = a.get("name")
        if tag == "input" and a.get("type") == "hidden" and name:
            self.fields[name] = a.get("value") or ""


def _user_agent() -> str:
    from ihalent import __version__

    return f"ihalent/{__version__}"


def _call(opener: Opener, req: urllib.request.Request) -> tuple[bytes, dict[str, str]]:
    try:
        resp = opener.open(req, timeout=60)
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 406, 428, 429, 503):
            raise AccessBlocked(
                f"the bulletin page refused the request (HTTP {exc.code}); not retrying"
            ) from exc
        raise FetchError(f"HTTP {exc.code} from the bulletin page") from exc
    except urllib.error.URLError as exc:
        raise FetchError(f"could not reach the bulletin page: {exc.reason}") from exc
    with resp:
        body = resp.read()
        headers = {k.lower(): v for k, v in resp.headers.items()}
    return body, headers


def _check_page(body: bytes) -> None:
    head = body[:200_000].decode("utf-8", errors="replace")
    if _VERIFICATION.search(head):
        raise AccessBlocked("the bulletin page now asks for human verification; stopping")


def fetch_bulletin(
    day: date,
    kind: TenderType,
    out_dir: str | Path,
    *,
    opener: Opener | None = None,
    today: date | None = None,
) -> FetchResult:
    """Download one day's bulletin of one tender type into ``out_dir``.

    Skips the download if the file is already there. Today's bulletin uses the
    page's own button; an earlier day goes through its archive form."""
    if kind not in TYPE_CODE:
        raise ValueError(f"no bulletin for tender type {kind.value!r}")
    out = Path(out_dir)
    target = out / bulletin_filename(day, kind)
    if target.is_file() and target.read_bytes()[:2] == b"PK":
        return FetchResult(day, target, downloaded=False)

    op: Opener = opener or default_opener()
    agent = {"User-Agent": _user_agent()}
    page, _ = _call(op, urllib.request.Request(BULLETIN_PAGE, headers=agent))
    _check_page(page)
    parser = _HiddenFields()
    parser.feed(page.decode("utf-8", errors="replace"))
    form = dict(parser.fields)
    if "__EVENTVALIDATION" not in form:
        raise NoBulletin("the bulletin page no longer has the expected form")

    if day == (today or date.today()):
        form.update({
            "__EVENTTARGET": _PREFIX + _TODAY_BUTTON[kind], "__EVENTARGUMENT": "",
            _TYPE_FIELD: "0", _DATE_FIELD: "",
        })
    else:
        form.update({
            "__EVENTTARGET": _ARCHIVE_BUTTON, "__EVENTARGUMENT": "",
            _TYPE_FIELD: TYPE_CODE[kind], _DATE_FIELD: f"{day:%d.%m.%Y}",
        })
    req = urllib.request.Request(
        BULLETIN_PAGE,
        data=urllib.parse.urlencode(form).encode("ascii"),
        headers={**agent, "Referer": BULLETIN_PAGE,
                 "Content-Type": "application/x-www-form-urlencoded"},
    )
    body, headers = _call(op, req)
    if body[:2] != b"PK":
        _check_page(body)
        raise NoBulletin(f"no {FILE_TAG[kind]} bulletin for {day:%d.%m.%Y} (the page sent no file)")
    m = re.search(r'filename="?([^";]+)', headers.get("content-disposition", ""))
    got = m.group(1).strip() if m else ""
    if got != target.name:
        raise NoBulletin(f"asked for {target.name} but the page sent {got or 'an unnamed file'}")
    out.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(".part")
    partial.write_bytes(body)
    partial.replace(target)
    return FetchResult(day, target, downloaded=True)


def weekdays(start: date, end: date) -> Iterator[date]:
    """Bulletins come out on working days; weekends are skipped. Public holidays
    are not known here: on those days the page simply has no file."""
    d = start
    while d <= end:
        if d.weekday() < 5:
            yield d
        d += timedelta(days=1)


@dataclass
class FetchReport:
    results: list[FetchResult]
    unavailable: list[tuple[date, str]]
    blocked: str | None = None  # verification or refusal: stop, do not retry
    failed: str | None = None  # network or server error: stopped, safe to run again later


def fetch_range(
    start: date,
    end: date,
    kind: TenderType,
    out_dir: str | Path,
    *,
    opener: Opener | None = None,
    today: date | None = None,
    pause: float = MIN_PAUSE_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
) -> FetchReport:
    """Fetch every working day from ``start`` to ``end``, one file at a time.

    Waits at least two seconds between downloads, skips files already on disk,
    records days with no bulletin and carries on, and stops at the first sign of
    verification or refusal."""
    report = FetchReport([], [])
    op: Opener = opener or default_opener()
    first = True
    for day in weekdays(start, end):
        target = Path(out_dir) / bulletin_filename(day, kind)
        if not (target.is_file() and target.read_bytes()[:2] == b"PK"):
            if not first:
                sleep(max(pause, MIN_PAUSE_SECONDS))
            first = False
        try:
            report.results.append(fetch_bulletin(day, kind, out_dir, opener=op, today=today))
        except AccessBlocked as exc:
            report.blocked = str(exc)
            break
        except NoBulletin as exc:
            report.unavailable.append((day, str(exc)))
        except FetchError as exc:
            report.failed = f"{day.isoformat()}: {exc}"
            break
    return report
