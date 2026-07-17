"""Rendering: terminal and JSON views of analytics.

Money is printed in Turkish grouping (1.234.567,89) because the audience reads
it that way; everything else stays ASCII so the output survives any Windows
console code page. The coverage line is never optional — if a statistic is
shown, the ground it stands on is shown next to it.
"""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

from ihalent.analytics import (
    Coverage,
    DiscountStats,
    FirmProfile,
    Overview,
)


def fmt_try(value: float | None) -> str:
    if value is None:
        return "-"
    s = f"{value:,.2f}"  # 1,234,567.89
    return s.replace(",", "_").replace(".", ",").replace("_", ".")  # -> 1.234.567,89


def fmt_pct(value: float | None) -> str:
    return "-" if value is None else f"{value:.2f}%"


def _coverage_note(cov: Coverage, what: str) -> str:
    if cov.excluded == 0:
        return f"based on all {cov.used} {what}"
    return (
        f"based on {cov.used} of {cov.considered} {what} "
        f"({cov.excluded} excluded for missing data)"
    )


def render_discount(stats: DiscountStats, console: Console) -> None:
    if stats.mean is None:
        console.print(
            f"[yellow]No discount could be computed for {stats.label}[/] "
            f"({_coverage_note(stats.coverage, 'awards')})."
        )
        return
    table = Table(title=f"Discount (kırım) — {stats.label}", title_justify="left")
    table.add_column("mean")
    table.add_column("median")
    table.add_column("min")
    table.add_column("max")
    table.add_row(
        fmt_pct(stats.mean), fmt_pct(stats.median), fmt_pct(stats.min), fmt_pct(stats.max)
    )
    console.print(table)
    console.print(f"[dim]{_coverage_note(stats.coverage, 'awards')}.[/dim]")


def render_firm(profile: FirmProfile, console: Console) -> None:
    console.print(f"\n[bold]{profile.name}[/bold]")
    console.print(
        f"  wins: {profile.wins}   "
        f"joint ventures: {profile.joint_ventures}   "
        f"total contract value: {fmt_try(profile.total_contract_try)} TL"
    )
    if profile.known_contract_count < profile.wins:
        console.print(
            f"  [dim]contract value known for {profile.known_contract_count} of "
            f"{profile.wins} wins; total is a floor, not the full figure.[/dim]"
        )
    if profile.distinct_spellings > 1:
        console.print(
            f"  [yellow]note:[/yellow] the query matched {profile.distinct_spellings} "
            f"distinct company spellings — narrow it if these are different firms."
        )
    render_discount(profile.discount, console)
    if profile.authorities:
        console.print("  top awarding authorities:")
        for name, n in sorted(profile.authorities.items(), key=lambda kv: -kv[1])[:5]:
            console.print(f"    {n:>3}x  {name}")


def render_overview(ov: Overview, console: Console) -> None:
    console.print("\n[bold]Dataset overview[/bold]")
    console.print(
        f"  {ov.total} tenders: {ov.awarded} awarded, {ov.cancelled} cancelled"
    )
    console.print(f"  total awarded value: {fmt_try(ov.total_contract_try)} TL")
    render_discount(ov.discount, console)
    comp = ov.competition
    if comp.mean_bids is not None:
        console.print(
            f"  competition: {comp.mean_bids} valid bids on average "
            f"(median {comp.median_bids}); "
            f"{comp.single_bid_share:.1%} of awards had a single valid bid"
        )
        console.print(f"  [dim]{_coverage_note(comp.coverage, 'awards')}.[/dim]")
    console.print(
        f"  [dim]data gaps: {ov.missing_estimate} awards without an estimate, "
        f"{ov.missing_bid_count} without a bid count.[/dim]"
    )
