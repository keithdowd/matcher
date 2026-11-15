"""Tests for Matching and DeferredAcceptance: known answers, oracle, properties."""

import pytest
from hypothesis import given, settings

from residency_match.matching import DeferredAcceptance, Matching
from tests.helpers import (
    applicant_optimal,
    blocking_pairs,
    make_market,
    markets,
    stable_matchings,
)


def test_matching_lookups_and_equality() -> None:
    """Lookups work in both directions and equality ignores input order."""
    m = Matching([("B", "P"), ("A", "P"), ("C", "Q")])
    assert m.program_of("A") == "P"
    assert m.program_of("Z") is None
    assert m.holders("P") == ("A", "B")
    assert m.holders("none") == ()
    assert m == Matching([("A", "P"), ("B", "P"), ("C", "Q")])


def test_matching_rejects_double_match() -> None:
    """An applicant in two pairs is refused."""
    with pytest.raises(ValueError):
        Matching([("A", "P"), ("A", "Q")])


def test_to_matches_attaches_ranks() -> None:
    """to_matches reports each side's rank of the other and rejects bad pairs."""
    mk = make_market({"A": ["P", "Q"]}, {"P": ["A"], "Q": ["A"]}, {"P": 1, "Q": 1})
    (match,) = Matching([("A", "Q")]).to_matches(mk)
    assert (match.applicant_rank, match.program_rank) == (2, 1)
    mk2 = make_market({"A": ["P"]}, {"P": []}, {"P": 1})
    with pytest.raises(ValueError):
        Matching([("A", "P")]).to_matches(mk2)


def test_known_answer_applicant_optimal() -> None:
    """Classic 2x2 instance with two stable matchings; DA picks applicants' best.

    A1 prefers P1, A2 prefers P2, while P1 prefers A2 and P2 prefers A1. Both the
    applicant-optimal (A1-P1, A2-P2) and program-optimal matchings are stable.
    """
    mk = make_market(
        {"A1": ["P1", "P2"], "A2": ["P2", "P1"]},
        {"P1": ["A2", "A1"], "P2": ["A1", "A2"]},
        {"P1": 1, "P2": 1},
    )
    result = DeferredAcceptance(mk).run()
    assert result == Matching([("A1", "P1"), ("A2", "P2")])


def test_known_answer_displacement_with_capacity() -> None:
    """A later, better proposer displaces a held applicant, who moves on."""
    mk = make_market(
        {"A1": ["P1", "P2"], "A2": ["P1"], "A3": ["P1", "P2"]},
        {"P1": ["A2", "A3", "A1"], "P2": ["A1", "A3"]},
        {"P1": 2, "P2": 1},
    )
    # Round 1: P1 holds A2, A3 (rejects A1); P2 gets nobody yet.
    # Round 2: A1 proposes to P2 and is held.
    assert DeferredAcceptance(mk).run() == Matching(
        [("A1", "P2"), ("A2", "P1"), ("A3", "P1")]
    )


def test_unranked_applicant_is_rejected_even_with_free_seats() -> None:
    """A program never takes an applicant it does not rank."""
    mk = make_market({"A": ["P"]}, {"P": []}, {"P": 3})
    assert DeferredAcceptance(mk).run().pairs == ()


def test_zero_capacity_and_empty_lists() -> None:
    """Zero-capacity programs and empty lists are valid and match nobody."""
    mk = make_market({"A": ["P"], "B": []}, {"P": ["A"]}, {"P": 0})
    assert DeferredAcceptance(mk).run().pairs == ()


def test_progress_callback_reports_rounds() -> None:
    """The callback fires once per round with a positive proposal count."""
    mk = make_market(
        {"A1": ["P1", "P2"], "A2": ["P1"]},
        {"P1": ["A2", "A1"], "P2": ["A1"]},
        {"P1": 1, "P2": 1},
    )
    seen: list[tuple[int, int]] = []
    DeferredAcceptance(mk).run(lambda r, n: seen.append((r, n)))
    assert seen == [(1, 2), (2, 1)]


@settings(max_examples=300, deadline=None)
@given(markets())
def test_matches_brute_force_applicant_optimal(market) -> None:  # type: ignore[no-untyped-def]
    """On small markets DA returns the stable matching applicants prefer most."""
    result = DeferredAcceptance(market).run()
    stable = stable_matchings(market)
    assert result in stable
    assert applicant_optimal(market, stable) == result


@settings(max_examples=300, deadline=None)
@given(markets(max_applicants=8, max_programs=5))
def test_random_markets_are_feasible_and_stable(market) -> None:  # type: ignore[no-untyped-def]
    """Output respects capacity and listings and has no blocking pair."""
    result = DeferredAcceptance(market).run()
    for aid, pid in result.pairs:
        assert market.is_acceptable(aid, pid)
    for p in market.programs:
        assert len(result.holders(p.program_id)) <= p.capacity
    assert blocking_pairs(market, result) == []
    # Deterministic: a fresh run gives the same answer.
    assert DeferredAcceptance(market).run() == result
