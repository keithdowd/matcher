"""Rich-based console output for the residency match simulator.

Each section of the display is one method of :class:`ConsoleReporter`. This
module only formats and prints; it reads no files and makes no matching
decisions. The Rich console is injected so tests can capture the text.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from residency_match.checks import CheckResult
from residency_match.market import Market
from residency_match.matching import Matching
from residency_match.models import ValidationIssue

#: Width of the fill bar in the programs table, in characters.
BAR_WIDTH = 10


def fill_bar(filled: int, capacity: int, width: int = BAR_WIDTH) -> str:
    """Render a text bar showing how full a program is.

    Parameters
    ----------
    filled : int
        Seats filled.
    capacity : int
        Total seats; zero gives an empty bar.
    width : int, default 10
        Bar length in characters.

    Returns
    -------
    str
        Filled blocks followed by empty blocks, e.g. ``"#####-----"``.
    """
    # ASCII characters keep the bar readable in logs and legacy terminals.
    n = round(width * filled / capacity) if capacity else 0
    return "#" * n + "-" * (width - n)


class ConsoleReporter:
    """Prints the sections of a run.

    Parameters
    ----------
    console : rich.console.Console
        Where to print. Rich drops color and the spinner when it is not a
        terminal, and ``Console(no_color=True)`` turns color off.
    quiet : bool, default False
        Suppress everything except :meth:`footer`, for scripts.

    Examples
    --------
    >>> reporter = ConsoleReporter(Console(quiet=True))
    >>> reporter.footer([], 0)
    """

    def __init__(self, console: Console, quiet: bool = False) -> None:
        """Store the console and quiet flag."""
        self._console = console
        self._quiet = quiet

    def _print(self, *renderables: object) -> None:
        """Print unless quiet."""
        if not self._quiet:
            self._console.print(*renderables)

    def header(self, seed: int | None, market: Market, now: datetime) -> None:
        """Print the header panel: seed, counts and time.

        Parameters
        ----------
        seed : int or None
            Run seed, or ``None`` if unknown.
        market : Market
            The loaded problem.
        now : datetime
            Time to show.
        """
        seed_text = "unknown" if seed is None else str(seed)
        body = (
            f"Seed: {seed_text}\n"
            f"Applicants: {len(market.applicants)}   "
            f"Programs: {len(market.programs)}\n"
            f"Time: {now.isoformat(timespec='seconds')}"
        )
        self._print(Panel(body, title="Residency Match", expand=False))

    def inputs_summary(self, market: Market) -> None:
        """Print applicant and seat totals and average ranking lengths."""
        n_a, n_p = len(market.applicants), len(market.programs)
        seats = sum(p.capacity for p in market.programs)
        a_avg = sum(len(v) for v in market.applicant_lists.values()) / n_a if n_a else 0
        p_avg = sum(len(v) for v in market.program_lists.values()) / n_p if n_p else 0
        table = Table(title="Inputs", show_header=False)
        table.add_row("Applicants", str(n_a))
        table.add_row("Seats", str(seats))
        table.add_row("Avg applicant list length", f"{a_avg:.1f}")
        table.add_row("Avg program list length", f"{p_avg:.1f}")
        self._print(table)

    @contextmanager
    def progress(self) -> Iterator[Callable[[int, int], None]]:
        """Show a live spinner that updates each round of proposals.

        Yields
        ------
        callable
            Pass to ``DeferredAcceptance.run`` as ``on_round``.
        """
        if self._quiet:
            yield lambda _round, _proposals: None
            return
        with self._console.status("Running deferred acceptance...") as status:

            def update(round_no: int, proposals: int) -> None:
                status.update(f"Round {round_no}: {proposals} proposals")

            yield update

    def matches_table(self, market: Market, matching: Matching) -> None:
        """Print one row per applicant.

        Rank 1 matches are green, lower ranks yellow, unmatched red.
        """
        table = Table(title="Matches")
        for col in ("Applicant", "Program", "Applicant rank", "Program rank"):
            table.add_column(col)
        by_applicant = {m.applicant_id: m for m in matching.to_matches(market)}
        for aid in sorted(a.applicant_id for a in market.applicants):
            m = by_applicant.get(aid)
            if m is None:
                table.add_row(aid, "UNMATCHED", "-", "-", style="red")
            else:
                style = "green" if m.applicant_rank == 1 else "yellow"
                table.add_row(
                    aid,
                    m.program_id,
                    str(m.applicant_rank),
                    str(m.program_rank),
                    style=style,
                )
        self._print(table)

    def programs_table(self, market: Market, matching: Matching) -> None:
        """Print capacity, filled and unfilled seats with a fill bar."""
        table = Table(title="Programs")
        for col in ("Program", "Capacity", "Filled", "Unfilled", "Fill"):
            table.add_column(col)
        for p in sorted(market.programs, key=lambda p: p.program_id):
            filled = len(matching.holders(p.program_id))
            table.add_row(
                p.program_id,
                str(p.capacity),
                str(filled),
                str(p.capacity - filled),
                fill_bar(filled, p.capacity),
            )
        self._print(table)

    def validation_panel(self, results: Sequence[CheckResult]) -> None:
        """Print one PASS or FAIL line per check, with problems indented."""
        lines: list[str] = []
        for r in results:
            if r.passed:
                lines.append(f"[green]PASS[/green]  {r.check}")
            else:
                lines.append(f"[red]FAIL[/red]  {r.check}")
                lines.extend(f"        {i.detail}" for i in r.issues)
        self._print(Panel("\n".join(lines), title="Validation", expand=False))

    def input_errors(self, issues: Sequence[ValidationIssue]) -> None:
        """Print every input problem to the error stream (never suppressed)."""
        err = Console(stderr=True, no_color=self._console.no_color)
        for issue in issues:
            err.print(f"error: {issue}", markup=False, highlight=False)

    def footer(self, paths: Sequence[Path], exit_status: int) -> None:
        """Print output paths and the exit status; shown even when quiet.

        Parameters
        ----------
        paths : Sequence[Path]
            Files written.
        exit_status : int
            The process exit status.
        """
        for path in paths:
            self._console.print(
                f"Wrote {path}", markup=False, highlight=False, soft_wrap=True
            )
        self._console.print(f"Exit status: {exit_status}", markup=False)
