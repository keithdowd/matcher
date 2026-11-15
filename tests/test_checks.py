"""Tests for the validation checks and the Validator."""

from hypothesis import given, settings

from residency_match.checks import (
    CapacityCheck,
    ListedPairsCheck,
    ReproducibilityCheck,
    SingleMatchCheck,
    StabilityCheck,
    Validator,
)
from residency_match.market import Market
from residency_match.matching import DeferredAcceptance, Matching
from tests.helpers import all_feasible_matchings, blocking_pairs, make_market, markets


def _market() -> Market:
    """Two applicants, two single-seat programs, full mutual lists."""
    return make_market(
        {"A1": ["P1", "P2"], "A2": ["P1", "P2"]},
        {"P1": ["A1", "A2"], "P2": ["A1", "A2"]},
        {"P1": 1, "P2": 1},
    )


def test_all_checks_pass_on_matcher_output() -> None:
    """A correct matching passes every check in the default validator."""
    mk = _market()
    results = Validator.default().run(mk, DeferredAcceptance(mk).run())
    assert [r.check for r in results] == [
        "Capacity",
        "Single match",
        "Listed pairs only",
        "Stability",
        "Reproducibility",
    ]
    assert all(r.passed for r in results)


def test_capacity_check_fails_when_over_capacity() -> None:
    """Two applicants in a one-seat program fail the capacity check."""
    issues = CapacityCheck().run(_market(), Matching([("A1", "P1"), ("A2", "P1")]))
    assert len(issues) == 1 and "P1" in issues[0].detail


def test_single_match_check_fails_on_duplicate_applicant() -> None:
    """An applicant matched twice fails the single-match check."""
    issues = SingleMatchCheck().run(_market(), Matching([("A1", "P1"), ("A1", "P2")]))
    assert len(issues) == 1 and "A1" in issues[0].detail


def test_listed_pairs_check_fails_on_unlisted_pair() -> None:
    """A pair the program does not rank fails the listed-pairs check."""
    mk = make_market({"A": ["P"]}, {"P": []}, {"P": 1})
    assert len(ListedPairsCheck().run(mk, Matching([("A", "P")]))) == 1
    assert len(ListedPairsCheck().run(mk, Matching([("A", "ghost")]))) == 1


def test_stability_check_finds_blocking_pair() -> None:
    """Leaving both applicants unmatched creates blocking pairs."""
    issues = StabilityCheck().run(_market(), Matching([]))
    assert {i.detail for i in issues} == {
        f"blocking pair: applicant {a}, program {p}"
        for a in ("A1", "A2")
        for p in ("P1", "P2")
    }


def test_stability_check_blocking_pair_displacing_worse_held() -> None:
    """A program that prefers an outsider to its holder is blocked."""
    # P1 holds A2, but A1 prefers P1 and P1 prefers A1.
    issues = StabilityCheck().run(_market(), Matching([("A2", "P1"), ("A1", "P2")]))
    assert [i.detail for i in issues] == ["blocking pair: applicant A1, program P1"]


def test_reproducibility_check_flags_a_different_matching() -> None:
    """A matching that differs from the matcher's own output is flagged."""
    mk = _market()
    assert ReproducibilityCheck().run(mk, DeferredAcceptance(mk).run()) == []
    assert len(ReproducibilityCheck().run(mk, Matching([]))) == 1


@settings(max_examples=200, deadline=None)
@given(markets())
def test_stability_check_agrees_with_brute_force(market) -> None:  # type: ignore[no-untyped-def]
    """On every feasible matching, StabilityCheck flags exactly the oracle's pairs."""
    check = StabilityCheck()
    for m in all_feasible_matchings(market):
        flagged = {i.detail for i in check.run(market, m)}
        expected = {
            f"blocking pair: applicant {a}, program {p}"
            for a, p in blocking_pairs(market, m)
        }
        assert flagged == expected
