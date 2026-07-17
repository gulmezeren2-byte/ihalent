"""Command line interface.

    ihalent overview  awards.jsonl
    ihalent firm      awards.jsonl "ACME İNŞAAT"
    ihalent discounts awards.jsonl --by authority --min 5
    ihalent parse     notice.md

The dataset commands read a JSONL file of awards (see `ihalent parse` and the
collector to produce one). Every command has a --json form for pipelines and
agents; the human form always prints the coverage behind each number.
"""

from __future__ import annotations

import contextlib
import json
import sys
from pathlib import Path

import typer
from rich.console import Console

import ihalent as _ihalent
from ihalent.analytics import by_group, firm_profile, overview
from ihalent.ingest import ingest_bundle
from ihalent.parse import NotAResultNotice, parse_result_notice
from ihalent.render import fmt_pct, render_firm, render_overview
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


@app.callback()
def _root(
    version: bool = typer.Option(
        False, "--version", "-V", callback=_version_callback, is_eager=True,
        help="Print the version and exit.",
    ),
) -> None:
    """ihalent — who won, for how much, at what discount, against how many bidders."""


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
    _console.print("[dim]awards column: used / considered (excluded lack an estimate).[/dim]")


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


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            with contextlib.suppress(Exception):  # pragma: no cover
                reconfigure(errors="replace")
    app()


if __name__ == "__main__":
    main()
