"""Command line interface.

    ihalent overview  awards.jsonl
    ihalent firm      awards.jsonl "ACME İNŞAAT"
    ihalent discounts awards.jsonl --by authority --min 5
    ihalent parse     notice.md
    ihalent fetch-bulletin --out bulletins
    ihalent ingest-bulletin bulletins -o awards.jsonl

The dataset commands read a JSONL file of awards (`ihalent ingest-bulletin`,
`ihalent ingest` and `ihalent parse` produce one). Every command has a --json form
for pipelines and agents; the human form always prints the coverage behind each number.
"""

from __future__ import annotations

import contextlib
import json
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.markup import escape

import ihalent as _ihalent
from ihalent.analytics import (
    by_group,
    concentration,
    firm_profile,
    overview,
    risk_flags,
    slice_awards,
)
from ihalent.ingest import ingest_bundle
from ihalent.parse import NotAResultNotice, parse_result_notice
from ihalent.render import (
    fmt_pct,
    fmt_try,
    render_concentration,
    render_firm,
    render_overview,
    render_risk,
)
from ihalent.store import dump_awards, load_awards

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
    help="Turkish public-tender award intelligence.",
)
_console = Console()
_err = Console(stderr=True)


def _version_callback(value: bool) -> None:
    if value:
        _console.print(f"ihalent {_ihalent.__version__}")
        raise typer.Exit()


def _use_utf8_output() -> None:
    """Make stdout/stderr able to carry the text this tool exists to print.

    Every report is full of Turkish — firm names like `ÖZKAN İNŞAAT LTD. ŞTİ.`,
    labels like `kırım` — and on Windows a *piped* stdout gets the legacy code page,
    where those characters raise UnicodeEncodeError and take the whole command down.
    `ihalent overview … | tee` must not crash, so ask for UTF-8 and never fail if the
    stream won't take it.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        with contextlib.suppress(OSError, ValueError):
            reconfigure(encoding="utf-8", errors="replace")


@app.callback()
def _root(
    version: bool = typer.Option(
        False, "--version", "-V", callback=_version_callback, is_eager=True,
        help="Print the version and exit.",
    ),
) -> None:
    """ihalent — who won, for how much, at what discount, against how many bidders."""
    _use_utf8_output()


def _load(path: Path) -> list:
    try:
        return load_awards(path)
    except (FileNotFoundError, ValueError) as exc:
        _err.print(f"[bold red]error:[/bold red] {exc}")
        raise typer.Exit(2) from exc


@app.command("overview")
def overview_cmd(
    awards: Path = typer.Argument(..., metavar="AWARDS.jsonl", help="JSONL of awards."),
    as_json: bool = typer.Option(False, "--json", help="Emit the overview as JSON."),
) -> None:
    """Summarize a dataset: value, discount, competition, and the data gaps."""
    data = _load(awards)
    ov = overview(data)
    if as_json:
        typer.echo(json.dumps(ov.to_dict(), ensure_ascii=True, indent=2))
    else:
        render_overview(ov, _console)


@app.command()
def firm(
    awards: Path = typer.Argument(..., metavar="AWARDS.jsonl"),
    name: str = typer.Argument(..., help="Company name (spelling variants fold together)."),
    as_json: bool = typer.Option(False, "--json", help="Emit the profile as JSON."),
) -> None:
    """Profile one company: its wins, total value, discount and where it wins."""
    data = _load(awards)
    profile = firm_profile(data, name)
    if profile is None:
        _err.print(f"[yellow]No awards found for a firm matching {name!r}.[/yellow]")
        raise typer.Exit(1)
    if as_json:
        typer.echo(json.dumps(profile.to_dict(), ensure_ascii=True, indent=2))
    else:
        render_firm(profile, _console)


@app.command()
def discounts(
    awards: Path = typer.Argument(..., metavar="AWARDS.jsonl"),
    by: str = typer.Option(
        "authority", "--by", help="Group by: authority | province | tender_type."
    ),
    min_awards: int = typer.Option(1, "--min", help="Hide groups thinner than this."),
    as_json: bool = typer.Option(False, "--json", help="Emit the table as JSON."),
) -> None:
    """Discount (kırım) distribution, grouped and sorted highest-mean first."""
    data = _load(awards)
    try:
        groups = by_group(data, by, min_awards=min_awards)
    except ValueError as exc:
        _err.print(f"[bold red]error:[/bold red] {exc}")
        raise typer.Exit(2) from exc
    if as_json:
        typer.echo(json.dumps([g.to_dict() for g in groups], ensure_ascii=True, indent=2))
        return
    if not groups:
        _console.print(f"[yellow]No groups with at least {min_awards} awards.[/yellow]")
        return
    from rich.table import Table

    table = Table(title=f"Mean discount by {by}", title_justify="left")
    table.add_column(by)
    table.add_column("mean", justify="right")
    table.add_column("median", justify="right")
    table.add_column("awards", justify="right")
    for g in groups:
        table.add_row(
            g.label, fmt_pct(g.mean), fmt_pct(g.median),
            f"{g.coverage.used}/{g.coverage.considered}",
        )
    _console.print(table)
    _console.print(
        "[dim]awards column: used / considered "
        "(excluded lack an estimate, or were awarded in lots).[/dim]"
    )


@app.command("single-bid")
def single_bid_cmd(
    awards: Path = typer.Argument(..., metavar="AWARDS.jsonl"),
    as_json: bool = typer.Option(False, "--json", help="Emit the flagged awards as JSON."),
) -> None:
    """List awards with a single valid bid — the ones with no real competition.

    A single-bid award is a flag procurement watchdogs care about: the winner
    faced no competing valid offer. Only awards whose bid count was published
    are considered, and the report says how many that was.
    """
    data = _load(awards)
    live = [a for a in data if not a.cancelled]
    known = [a for a in live if a.valid_bid_count is not None]
    flagged = [a for a in known if a.single_bid]
    if as_json:
        typer.echo(
            json.dumps(
                {
                    "considered": len(live),
                    "with_known_bid_count": len(known),
                    "single_bid_count": len(flagged),
                    "awards": [a.to_dict() for a in flagged],
                },
                ensure_ascii=True,
                indent=2,
            )
        )
        return
    if not flagged:
        _console.print(
            f"No single-bid awards among the {len(known)} with a published bid count."
        )
        return
    from rich.table import Table

    table = Table(title="Single-bid awards — no competing valid offer", title_justify="left")
    table.add_column("İKN")
    table.add_column("authority", overflow="fold")
    table.add_column("winner", overflow="fold")
    table.add_column("contract TL", justify="right")
    for a in flagged:
        table.add_row(a.ikn, a.authority or "-", a.winner or "-", fmt_try(a.contract_try))
    _console.print(table)
    _console.print(
        f"[dim]{len(flagged)} of {len(known)} awards with a published bid count "
        f"had a single valid bid.[/dim]"
    )


@app.command("concentration")
def concentration_cmd(
    awards: Path = typer.Argument(..., metavar="AWARDS.jsonl"),
    authority: str | None = typer.Option(
        None, "--authority", help="Limit to authorities whose name contains this text."
    ),
    province: str | None = typer.Option(
        None, "--province", help="Limit to a province (substring match)."
    ),
    top: int = typer.Option(5, "--top", help="How many leading firms to list."),
    as_json: bool = typer.Option(False, "--json", help="Emit as JSON."),
) -> None:
    """Winner concentration (HHI) over a dataset, or within one authority.

    single-bid flags a lack of competition *within* a tender; this flags it
    *across* tenders — whether the same few firms win everything a buyer puts
    out. Reports the Herfindahl-Hirschman Index (0..1) over win counts and the
    leading firms, with the coverage it stands on. High concentration in a small
    slice is arithmetic, not evidence; it is a place to look, not a conclusion.
    """
    data = _load(awards)
    subset, label = slice_awards(data, authority=authority, province=province)
    conc = concentration(subset, label=label, top=top)
    if as_json:
        typer.echo(json.dumps(conc.to_dict(), ensure_ascii=True, indent=2))
    else:
        render_concentration(conc, _console)


@app.command()
def flags(
    awards: Path = typer.Argument(..., metavar="AWARDS.jsonl"),
    low_discount: float = typer.Option(
        3.0,
        "--low-discount",
        help="Discount %% at/below which a contract counts as 'near the estimate'.",
    ),
    as_json: bool = typer.Option(False, "--json", help="Emit the flagged awards as JSON."),
) -> None:
    """Per-award procurement red flags — the signals transparency work looks for.

    Flags an award for a single valid bid, a price that landed at or above the
    public estimate, a missing estimate (so it can't be audited), or a tender many
    firms took documents for but almost none bid on. None is proof of anything; each
    is a reason to open the file. Awards raising the most flags (and the most money)
    come first.
    """
    data = _load(awards)
    report = risk_flags(data, low_discount_pct=low_discount)
    if as_json:
        typer.echo(json.dumps(report.to_dict(), ensure_ascii=True, indent=2))
    else:
        render_risk(report, _console)


@app.command()
def parse(
    notice: Path = typer.Argument(..., help="A result-notice (Sonuç İlanı) markdown/txt file."),
) -> None:
    """Parse one result notice to structured JSON on stdout."""
    if not notice.is_file():
        _err.print(f"[bold red]error:[/bold red] file not found: {notice}")
        raise typer.Exit(2)
    text = notice.read_text(encoding="utf-8")
    try:
        award = parse_result_notice(text)
    except NotAResultNotice as exc:
        _err.print(f"[bold red]error:[/bold red] {exc}")
        raise typer.Exit(2) from exc
    typer.echo(json.dumps(award.to_dict(), ensure_ascii=True, indent=2))


@app.command()
def ingest(
    bundle: Path = typer.Argument(..., help="JSON collected from ihale-mcp / EKAP."),
    out: Path = typer.Option(Path("awards.jsonl"), "--out", "-o", help="Where to write awards."),
) -> None:
    """Turn collected ihale-mcp/EKAP output into an awards JSONL file.

    Accepts a get_tender_announcements object, a list of them, or a list of
    {tender, announcements} pairs. Tenders without a result notice are skipped.
    """
    if not bundle.is_file():
        _err.print(f"[bold red]error:[/bold red] file not found: {bundle}")
        raise typer.Exit(2)
    try:
        data = json.loads(bundle.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        _err.print(f"[bold red]error:[/bold red] {bundle} is not valid JSON: {exc}")
        raise typer.Exit(2) from exc
    awards = ingest_bundle(data)
    if not awards:
        _err.print("[yellow]No result notices found in the bundle.[/yellow]")
        raise typer.Exit(1)
    n = dump_awards(awards, out)
    _console.print(f"wrote {out} — {n} award(s) with result notices")


def _bulletin_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for p in paths:
        if p.is_dir():
            files += sorted(
                f for f in p.iterdir()
                if f.suffix.lower() == ".zip" or f.name.upper().endswith("_SONUC.PDF")
            )
        elif p.is_file():
            files.append(p)
        else:
            _err.print(f"[bold red]error:[/bold red] not found: {p}")
            raise typer.Exit(2)
    return files


@app.command("ingest-bulletin")
def ingest_bulletin_cmd(
    paths: list[Path] = typer.Argument(
        ..., help="Bulletin ZIPs or *_SONUC.pdf files, or folders of them."
    ),
    out: Path = typer.Option(Path("awards.jsonl"), "--out", "-o", help="Where to write awards."),
    as_json: bool = typer.Option(False, "--json", help="Print the per-file check as JSON."),
) -> None:
    """Read Kamu İhale Bülteni result notices into an awards JSONL file.

    Give it every bulletin collected so far, not one day: a tender's lots are
    published on different days, and the file is rebuilt from all of them.
    Each file is checked against its own table of contents; the command exits 1
    if any notice could not be read or the counts disagree."""
    from ihalent.bulletin import (
        BulletinError,
        BulletinRead,
        MissingExtra,
        awards_from_reads,
        read_bulletin,
    )

    files = _bulletin_files(paths)
    if not files:
        _err.print("[yellow]No bulletin files found.[/yellow]")
        raise typer.Exit(1)
    reads: list[BulletinRead] = []
    for f in files:
        try:
            got = read_bulletin(f)
        except MissingExtra as exc:  # escaped: "[bulletin]" is not markup
            _err.print(f"[bold red]error:[/bold red] {escape(str(exc))}")
            raise typer.Exit(2) from exc
        except (BulletinError, OSError) as exc:
            _err.print(f"[bold red]error:[/bold red] {escape(str(exc))}")
            raise typer.Exit(2) from exc
        # A ZIP and the PDF unpacked from it are one file: report it once.
        reads += [r for r in got if r.source not in {s.source for s in reads}]
    awards = awards_from_reads(reads)
    n = dump_awards(awards, out)
    incomplete = [r for r in reads if not r.complete]
    if as_json:
        typer.echo(json.dumps(
            {"files": [r.to_dict() for r in reads], "awards": n, "out": str(out)},
            ensure_ascii=True, indent=2,
        ))
    else:
        for r in reads:
            mark = "ok" if r.complete else "[bold red]CHECK[/bold red]"
            _console.print(
                f"{mark}  {r.source}: {len(r.notices)} notice(s) read, "
                f"{len(r.rejected)} rejected, contents list {len(r.toc_ikns)}"
                + (f", missing {len(r.missing)}" if r.missing else "")
                + (f", unlisted {len(r.unlisted)}" if r.unlisted else "")
            )
            for rej in r.rejected:
                _console.print(f"      notice {rej.position} (page {rej.page}): {rej.reason}")
        lots = sum(1 for a in awards if a.lots_unverified)
        _console.print(
            f"wrote {out} — {n} tender(s)"
            + (f"; {lots} awarded in lots, so no discount for them" if lots else "")
        )
    if incomplete:
        raise typer.Exit(1)


@app.command("fetch-bulletin")
def fetch_bulletin_cmd(
    out: Path = typer.Option(Path("bulletins"), "--out", "-o", help="Folder to keep the files in."),
    day: str | None = typer.Option(None, "--date", help="YYYY-MM-DD; default today."),
    since: str | None = typer.Option(
        None, "--since", help="Also fetch every working day from this date (YYYY-MM-DD)."
    ),
    kind: str = typer.Option("yapim", "--type", help="yapim | mal | hizmet | danismanlik."),
) -> None:
    """Download Kamu İhale Bülteni files from EKAP's public bulletin page.

    One file per working day and tender type, at least two seconds apart, never
    twice. It stops, without retrying, if the page asks for human verification
    or refuses the request (exit 3), or on a network or server error (exit 4).
    Days with no bulletin are listed (exit 1)."""
    from datetime import date as _date

    from ihalent.fetch import TYPE_CODE, fetch_range
    from ihalent.model import TenderType

    try:
        tender_type = TenderType(kind)
        if tender_type not in TYPE_CODE:
            raise ValueError
        end = _date.fromisoformat(day) if day else _date.today()
        start = _date.fromisoformat(since) if since else end
    except ValueError as exc:
        _err.print("[bold red]error:[/bold red] check --type and the YYYY-MM-DD dates")
        raise typer.Exit(2) from exc
    if start > end:
        _err.print("[bold red]error:[/bold red] --since is after --date")
        raise typer.Exit(2)
    report = fetch_range(start, end, tender_type, out)
    for r in report.results:
        _console.print(f"{'got ' if r.downloaded else 'have'}  {r.path}")
    for d, why in report.unavailable:
        _console.print(f"none  {d.isoformat()}: {why}")
    if report.blocked:
        _err.print(f"[bold red]stopped:[/bold red] {escape(report.blocked)}")
        raise typer.Exit(3)
    if report.failed:
        _err.print(f"[bold red]failed:[/bold red] {escape(report.failed)}")
        raise typer.Exit(4)
    if report.unavailable:
        raise typer.Exit(1)


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            with contextlib.suppress(Exception):  # pragma: no cover
                reconfigure(errors="replace")
    app()


if __name__ == "__main__":
    main()
