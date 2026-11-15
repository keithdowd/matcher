"""Tests for Market: rank lookups, acceptability and construction rules."""

import pytest

from residency_match.market import Market
from residency_match.models import Applicant, Program


def _market() -> Market:
    """Build a small hand-checked market (A1 lists P1,P2; P2 ranks only A2)."""
    return Market(
        [Applicant("A1", 2), Applicant("A2", 1)],
        [Program("P1", 1), Program("P2", 0)],
        {"A1": ["P2", "P1"], "A2": ["P2"]},
        {"P1": ["A1"], "P2": ["A2"]},
    )


def test_rank_lookups_are_one_based() -> None:
    """Rank 1 is the first list entry; unlisted pairs give None."""
    m = _market()
    assert m.applicant_rank("A1", "P2") == 1
    assert m.applicant_rank("A1", "P1") == 2
    assert m.applicant_rank("A2", "P1") is None
    assert m.program_rank("P1", "A1") == 1
    assert m.program_rank("P1", "A2") is None


def test_acceptable_requires_both_sides() -> None:
    """A pair is acceptable only if each side lists the other."""
    m = _market()
    assert m.is_acceptable("A1", "P1")
    assert m.is_acceptable("A2", "P2")
    # A1 lists P2, but P2 does not rank A1.
    assert not m.is_acceptable("A1", "P2")
    assert m.acceptable_pairs() == [("A1", "P1"), ("A2", "P2")]


def test_capacity_and_lottery_lookups() -> None:
    """Capacity and lottery values come back as given, zero capacity included."""
    m = _market()
    assert m.capacity("P2") == 0
    assert m.lottery("A1") == 2


def test_missing_lists_default_to_empty() -> None:
    """Applicants and programs absent from the mappings have empty lists."""
    m = Market([Applicant("A", 1)], [Program("P", 1)], {}, {})
    assert m.applicant_lists["A"] == ()
    assert m.program_lists["P"] == ()
    assert m.acceptable_pairs() == []


def test_lists_are_read_only() -> None:
    """The stored lists cannot be mutated."""
    m = _market()
    with pytest.raises(TypeError):
        m.applicant_lists["A1"] = ()  # type: ignore[index]


@pytest.mark.parametrize(
    ("a_lists", "p_lists"),
    [
        ({"A": ["X"]}, {}),  # unknown program in applicant list
        ({}, {"P": ["X"]}),  # unknown applicant in program list
        ({"A": ["P", "P"]}, {}),  # repeated entry
        ({"Z": ["P"]}, {}),  # list for unknown applicant
    ],
)
def test_invalid_construction_is_rejected(
    a_lists: dict[str, list[str]], p_lists: dict[str, list[str]]
) -> None:
    """Unknown ids and repeated entries raise ValueError."""
    with pytest.raises(ValueError):
        Market([Applicant("A", 1)], [Program("P", 1)], a_lists, p_lists)


def test_duplicate_ids_are_rejected() -> None:
    """Duplicate applicant or program ids raise ValueError."""
    with pytest.raises(ValueError):
        Market([Applicant("A", 1), Applicant("A", 2)], [], {}, {})
    with pytest.raises(ValueError):
        Market([], [Program("P", 1), Program("P", 2)], {}, {})
