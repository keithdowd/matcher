"""Tests for ConsoleReporter output text and styling."""

from datetime import datetime
from pathlib import Path

from rich.console import Console

from residency_match.checks import CheckResult, Validator
from residency_match.console import ConsoleReporter, fill_bar
from residency_match.market import Market
from residency_match.matching import DeferredAcceptance
from residency_match.models import ValidationIssue
from tests.helpers import make_market

NOW = datetime(2026, 11, 15, 9, 0, 0)


def _market() -> Market:
    """Build a market with a rank 1 match, a rank 2 match and an unmatched applicant."""
    return make_market(
        {"A1": ["P1"], "A2": ["P1", "P2"], "A3": ["P1"]},
        {"P1": ["A1", "A2", "A3"], "P2": ["A2"]},
        {"P1": 1, "P2": 2},
    )


def _plain(quiet: bool = False) -> tuple[Console, ConsoleReporter]:
    """Return a recording, colorless console and a reporter on it."""
    console = Console(record=True, width=100, force_terminal=False, color_system=None)
    return console, ConsoleReporter(console, quiet=quiet)


def test_fill_bar() -> None:
    """The bar scales with fill and handles zero capacity."""
    assert fill_bar(0, 4) == "-" * 10
    assert fill_bar(2, 4) == "#####-----"
    assert fill_bar(4, 4) == "#" * 10
    assert fill_bar(0, 0) == "-" * 10


def test_header_and_inputs_summary_text() -> None:
    """Header shows seed, counts and time; inputs shows totals and averages."""
    console, rep = _plain()
    market = _market()
    rep.header(42, market, NOW)
    rep.inputs_summary(market)
    text = console.export_text()
    assert "Seed: 42" in text
    assert "Applicants: 3" in text and "Programs: 2" in text
    assert "2026-11-15T09:00:00" in text
    assert "Seats" in text and "3" in text
    assert "1.3" in text  # average applicant list length (4 entries / 3)
    assert "Avg program list length" in text


def test_header_unknown_seed() -> None:
    """A missing seed is shown as unknown."""
    console, rep = _plain()
    rep.header(None, _market(), NOW)
    assert "Seed: unknown" in console.export_text()


def test_matches_and_programs_tables_text() -> None:
    """Tables show matches, UNMATCHED for the loser, and seat counts."""
    console, rep = _plain()
    market = _market()
    matching = DeferredAcceptance(market).run()
    rep.matches_table(market, matching)
    rep.programs_table(market, matching)
    text = console.export_text()
    assert "UNMATCHED" in text
    assert "A1" in text and "P2" in text
    assert "#" in text  # a fill bar is drawn


def test_matches_table_colors() -> None:
    """Rank 1 green, lower rank yellow, unmatched red."""
    console = Console(
        record=True, width=100, force_terminal=True, color_system="standard"
    )
    rep = ConsoleReporter(console)
    market = _market()
    rep.matches_table(market, DeferredAcceptance(market).run())
    html = console.export_html()
    assert "color: #008000" in html  # green
    assert "color: #800000" in html  # red


def test_validation_panel_pass_and_fail() -> None:
    """Each check gets a PASS/FAIL line and failing issues are listed."""
    console, rep = _plain()
    rep.validation_panel(
        [
            CheckResult("Capacity", ()),
            CheckResult("Stability", (ValidationIssue("Stability", "A1 P1"),)),
        ]
    )
    text = console.export_text()
    assert "PASS  Capacity" in text
    assert "FAIL  Stability" in text
    assert "A1 P1" in text


def test_validation_panel_on_real_results() -> None:
    """The panel renders results from the real validator."""
    console, rep = _plain()
    market = _market()
    rep.validation_panel(
        Validator.default().run(market, DeferredAcceptance(market).run())
    )
    assert console.export_text().count("PASS") == 5


def test_footer_lists_paths_and_status() -> None:
    """The footer shows each path and the exit status."""
    console, rep = _plain()
    rep.footer([Path("results/matches.csv")], 1)
    text = console.export_text()
    assert "Wrote results" in text and "matches.csv" in text
    assert "Exit status: 1" in text


def test_quiet_suppresses_everything_but_footer() -> None:
    """In quiet mode only the footer is printed."""
    console, rep = _plain(quiet=True)
    market = _market()
    matching = DeferredAcceptance(market).run()
    rep.header(1, market, NOW)
    rep.inputs_summary(market)
    with rep.progress() as on_round:
        on_round(1, 3)
    rep.matches_table(market, matching)
    rep.programs_table(market, matching)
    rep.validation_panel([CheckResult("Capacity", ())])
    assert console.export_text() == ""
    rep.footer([], 0)
    assert console.export_text().strip() == "Exit status: 0"


def test_progress_callback_runs_without_a_terminal() -> None:
    """The spinner callback is safe on a non-terminal console."""
    console, rep = _plain()
    market = _market()
    with rep.progress() as on_round:
        DeferredAcceptance(market).run(on_round)
