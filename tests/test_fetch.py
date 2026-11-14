"""Bulletin download tests, offline: a fake opener stands in for EKAP's page."""

from __future__ import annotations

import io
import ssl
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from email.message import Message
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from ihalent import fetch
from ihalent.cli import app
from ihalent.fetch import (
    AccessBlocked,
    NoBulletin,
    bulletin_filename,
    fetch_bulletin,
    fetch_range,
    weekdays,
)
from ihalent.model import TenderType

PAGE = b"""<html><body><form method="post" action="./bultenindirme.aspx" id="aspnetForm">
<input type="hidden" name="__EVENTTARGET" id="__EVENTTARGET" value="" />
<input type="hidden" name="__VIEWSTATE" id="__VIEWSTATE" value="" />
<input type="hidden" name="__EVENTVALIDATION" id="__EVENTVALIDATION" value="abc123" />
<select name="ctl00$ContentPlaceHolder1$ddlstBxIhaleTur">
<option value="0">Se\xc3\xa7iniz</option></select>
</form></body></html>"""

TODAY = date(2026, 11, 13)  # a Friday


class FakeResponse(io.BytesIO):
    def __init__(self, body: bytes, headers: dict[str, str] | None = None) -> None:
        super().__init__(body)
        self.headers = Message()
        for k, v in (headers or {}).items():
            self.headers[k] = v


class FakeOpener:
    """Answers GET with the form page and POST with whatever ``serve`` returns."""

    def __init__(self, serve: Any, page: bytes = PAGE) -> None:
        self.serve = serve
        self.page = page
        self.posts: list[dict[str, str]] = []
        self.calls = 0

    def open(self, req: urllib.request.Request, timeout: float = 0) -> FakeResponse:
        self.calls += 1
        if req.data is None:
            return FakeResponse(self.page)
        form = dict(urllib.parse.parse_qsl(req.data.decode("ascii"), keep_blank_values=True))
        self.posts.append(form)
        result = self.serve(form)
        if isinstance(result, Exception):
            raise result
        return result


def zip_named(name: str) -> FakeResponse:
    return FakeResponse(b"PK\x03\x04fake", {"Content-Disposition": f"attachment;filename={name}"})


def test_todays_bulletin_uses_the_pages_button(tmp_path: Path) -> None:
    op = FakeOpener(lambda form: zip_named("BULTEN_13112026_YAPIM.zip"))
    res = fetch_bulletin(TODAY, TenderType.WORKS, tmp_path, opener=op, today=TODAY)
    assert res.downloaded
    assert res.path.name == "BULTEN_13112026_YAPIM.zip"
    assert res.path.read_bytes().startswith(b"PK")
    (form,) = op.posts
    assert form["__EVENTTARGET"] == "ctl00$ContentPlaceHolder1$lnkBtnYapim"
    assert form["__EVENTVALIDATION"] == "abc123"
    # The type list must be sent as '0', or the page answers with an error page.
    assert form["ctl00$ContentPlaceHolder1$ddlstBxIhaleTur"] == "0"


def test_an_earlier_day_goes_through_the_archive_form(tmp_path: Path) -> None:
    op = FakeOpener(lambda form: zip_named("BULTEN_10112026_YAPIM.zip"))
    fetch_bulletin(date(2026, 11, 10), TenderType.WORKS, tmp_path, opener=op, today=TODAY)
    (form,) = op.posts
    assert form["__EVENTTARGET"] == "ctl00$ContentPlaceHolder1$btnYukle"
    assert form["ctl00$ContentPlaceHolder1$ddlstBxIhaleTur"] == "2"
    key = "ctl00$ContentPlaceHolder1$etBultenTarihi$EkapTakvimTextBox_etBultenTarihi"
    assert form[key] == "10.11.2026"


def test_the_wrong_day_is_refused_not_kept(tmp_path: Path) -> None:
    # A malformed request makes the page serve today's file instead.
    op = FakeOpener(lambda form: zip_named("BULTEN_13112026_YAPIM.zip"))
    with pytest.raises(NoBulletin, match="BULTEN_10112026_YAPIM.zip"):
        fetch_bulletin(date(2026, 11, 10), TenderType.WORKS, tmp_path, opener=op, today=TODAY)
    assert not list(tmp_path.iterdir())


def test_an_error_page_means_no_bulletin(tmp_path: Path) -> None:
    op = FakeOpener(lambda form: FakeResponse(b"<html>Hata</html>"))
    with pytest.raises(NoBulletin):
        fetch_bulletin(date(2026, 11, 10), TenderType.WORKS, tmp_path, opener=op, today=TODAY)


def test_a_verification_screen_stops_everything(tmp_path: Path) -> None:
    page = b'<html><div class="cf-turnstile" data-sitekey="x"></div></html>'
    op = FakeOpener(lambda form: zip_named("x.zip"), page=page)
    with pytest.raises(AccessBlocked):
        fetch_bulletin(TODAY, TenderType.WORKS, tmp_path, opener=op, today=TODAY)
    assert op.posts == []  # nothing was submitted to the verification page


@pytest.mark.parametrize("code", [403, 428, 429])
def test_a_refusal_is_not_retried(tmp_path: Path, code: int) -> None:
    def refuse(form: dict[str, str]) -> Exception:
        return urllib.error.HTTPError(fetch.BULLETIN_PAGE, code, "no", Message(), None)

    op = FakeOpener(refuse)
    with pytest.raises(AccessBlocked):
        fetch_bulletin(TODAY, TenderType.WORKS, tmp_path, opener=op, today=TODAY)
    assert len(op.posts) == 1


def test_a_file_already_on_disk_is_not_downloaded_again(tmp_path: Path) -> None:
    (tmp_path / bulletin_filename(TODAY, TenderType.WORKS)).write_bytes(b"PK\x03\x04old")
    op = FakeOpener(lambda form: zip_named("BULTEN_13112026_YAPIM.zip"))
    res = fetch_bulletin(TODAY, TenderType.WORKS, tmp_path, opener=op, today=TODAY)
    assert not res.downloaded
    assert op.calls == 0


def test_a_range_skips_weekends_paces_itself_and_stops_when_blocked(tmp_path: Path) -> None:
    assert [d.day for d in weekdays(date(2026, 11, 6), date(2026, 11, 10))] == [6, 9, 10]

    def serve(form: dict[str, str]) -> Any:
        day = form.get("ctl00$ContentPlaceHolder1$etBultenTarihi$EkapTakvimTextBox_etBultenTarihi")
        if day == "09.11.2026":
            return FakeResponse(b"<html>yok</html>")  # e.g. a public holiday
        if day == "11.11.2026":
            return urllib.error.HTTPError(fetch.BULLETIN_PAGE, 428, "no", Message(), None)
        stamp = day.replace(".", "") if day else "13112026"
        return zip_named(f"BULTEN_{stamp}_YAPIM.zip")

    waits: list[float] = []
    report = fetch_range(
        date(2026, 11, 6), date(2026, 11, 13), TenderType.WORKS, tmp_path,
        opener=FakeOpener(serve), today=TODAY, pause=0.0, sleep=waits.append,
    )
    assert [r.day.day for r in report.results] == [6, 10]
    assert [d.day for d, _ in report.unavailable] == [9]
    assert report.blocked  # stopped on the 11th; the 12th and 13th were not tried
    assert all(w >= fetch.MIN_PAUSE_SECONDS for w in waits)


def test_a_network_error_stops_the_range_and_keeps_the_report(tmp_path: Path) -> None:
    def serve(form: dict[str, str]) -> Any:
        day = form.get("ctl00$ContentPlaceHolder1$etBultenTarihi$EkapTakvimTextBox_etBultenTarihi")
        if day == "10.11.2026":
            return urllib.error.HTTPError(fetch.BULLETIN_PAGE, 500, "boom", Message(), None)
        return zip_named(f"BULTEN_{day.replace('.', '')}_YAPIM.zip")

    report = fetch_range(
        date(2026, 11, 9), date(2026, 11, 11), TenderType.WORKS, tmp_path,
        opener=FakeOpener(serve), today=TODAY, sleep=lambda s: None,
    )
    assert [r.day.day for r in report.results] == [9]
    assert report.failed and "2026-11-10" in report.failed
    assert report.blocked is None


_TYPE_KEY = "ctl00$ContentPlaceHolder1$ddlstBxIhaleTur"
_DATE_KEY = "ctl00$ContentPlaceHolder1$etBultenTarihi$EkapTakvimTextBox_etBultenTarihi"
_TAG = {"1": "MAL", "2": "YAPIM", "3": "HIZMET", "4": "DANISMANLIK"}


def _archive(form: dict[str, str]) -> Any:
    return zip_named(f"BULTEN_{form[_DATE_KEY].replace('.', '')}_{_TAG[form[_TYPE_KEY]]}.zip")


def test_several_types_keep_the_pause_between_every_download(tmp_path: Path) -> None:
    waits: list[float] = []
    report = fetch_range(
        date(2026, 11, 11), date(2026, 11, 12), list(fetch.TYPE_CODE), tmp_path,
        opener=FakeOpener(_archive), today=TODAY, pause=0.0, sleep=waits.append,
    )
    assert len(report.results) == 8  # two days, four types
    assert len(waits) == 7  # before every download but the first, across types too
    assert all(w >= fetch.MIN_PAUSE_SECONDS for w in waits)


def test_a_block_on_one_type_stops_every_type(tmp_path: Path) -> None:
    def serve(form: dict[str, str]) -> Any:
        if form[_TYPE_KEY] == "2":
            return urllib.error.HTTPError(fetch.BULLETIN_PAGE, 428, "no", Message(), None)
        return _archive(form)

    op = FakeOpener(serve)
    report = fetch_range(
        date(2026, 11, 12), date(2026, 11, 12), list(fetch.TYPE_CODE), tmp_path,
        opener=op, today=TODAY, sleep=lambda s: None,
    )
    assert [r.path.name for r in report.results] == ["BULTEN_12112026_MAL.zip"]
    assert report.blocked
    assert len(op.posts) == 2  # goods, then works refused; service and consultancy not asked


def _report(have: int = 1, **kw: Any) -> fetch.FetchReport:
    results = [fetch.FetchResult(date(2026, 11, 13), Path("x.zip"), downloaded=False)] * have
    return fetch.FetchReport(results, [], **kw)


def test_daily_says_when_a_whole_week_brought_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A changed page answers every day with "no bulletin"; a holiday-free week
    # without a single file must not look like a quiet success.
    monkeypatch.setattr(fetch, "fetch_range", lambda *a, **k: _report(have=0))
    res = CliRunner().invoke(app, ["daily", str(tmp_path / "ekap")])
    assert res.exit_code == 1
    assert "nothing" in res.output


def test_daily_fills_in_the_last_week_of_every_type(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[Any, ...]] = []

    def fake_range(start: date, end: date, kinds: Any, out_dir: Any, **kw: Any) -> Any:
        calls.append((start, end, list(kinds), Path(out_dir)))
        return _report()

    monkeypatch.setattr(fetch, "fetch_range", fake_range)
    res = CliRunner().invoke(app, ["daily", str(tmp_path / "ekap")])
    assert res.exit_code == 0, res.output
    ((start, end, kinds, out),) = calls
    assert end == date.today() and (end - start).days == 6
    assert set(kinds) == set(fetch.TYPE_CODE)
    assert out == tmp_path / "ekap"


def test_daily_after_a_block_does_not_contact_the_page_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "ekap"
    runner = CliRunner()
    blocked = "the bulletin page now asks for human verification; stopping"
    monkeypatch.setattr(fetch, "fetch_range", lambda *a, **k: _report(blocked=blocked))
    first = runner.invoke(app, ["daily", str(folder)])
    assert first.exit_code == 3
    assert blocked in (folder / "ihalent-stopped.txt").read_text(encoding="utf-8")

    def must_not_run(*a: Any, **k: Any) -> Any:
        raise AssertionError("the page was contacted after a block")

    monkeypatch.setattr(fetch, "fetch_range", must_not_run)
    again = runner.invoke(app, ["daily", str(folder)])
    assert again.exit_code == 3, again.output

    (folder / "ihalent-stopped.txt").unlink()  # the user decides to try again
    monkeypatch.setattr(fetch, "fetch_range", lambda *a, **k: _report())
    assert runner.invoke(app, ["daily", str(folder)]).exit_code == 0


def test_daily_reads_the_folder_and_says_when_a_file_needs_a_look(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ihalent import bulletin

    reads = {"a.zip": bulletin.BulletinRead("A_SONUC.pdf", toc_ikns=[])}  # no contents list
    monkeypatch.setattr(bulletin, "read_bulletin", lambda p: [reads[Path(p).name]])
    monkeypatch.setattr(fetch, "fetch_range", lambda *a, **k: _report(failed="boom"))
    folder = tmp_path / "ekap"
    folder.mkdir()
    (folder / "a.zip").write_bytes(b"PK")
    res = CliRunner().invoke(app, ["daily", str(folder)])
    assert res.exit_code == 4  # the network error wins; the read still ran
    assert (folder / "awards.jsonl").is_file()
    assert "CHECK" in res.output

    monkeypatch.setattr(fetch, "fetch_range", lambda *a, **k: _report())
    assert CliRunner().invoke(app, ["daily", str(folder)]).exit_code == 1


def test_tls_adds_only_the_servers_suite_and_keeps_checks_on() -> None:
    ctx = fetch._tls_context()
    names = {c["name"] for c in ctx.get_ciphers()}
    assert "AES128-GCM-SHA256" in names
    assert ctx.verify_mode is ssl.CERT_REQUIRED
    assert ctx.check_hostname
