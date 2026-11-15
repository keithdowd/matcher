"""Tests for the dataclasses in models.py and the exceptions in errors.py."""

import dataclasses

import pytest

from residency_match.errors import InputError, ResidencyMatchError, UsageError
from residency_match.models import (
    Applicant,
    GeneratorConfig,
    Match,
    Program,
    ValidationIssue,
)


def test_applicant_rejects_empty_id() -> None:
    """An applicant with an empty identifier is refused."""
    with pytest.raises(ValueError):
        Applicant("", 1)


def test_program_invariants() -> None:
    """A program needs an id and a non-negative capacity; zero is valid."""
    assert Program("P", 0).capacity == 0
    with pytest.raises(ValueError):
        Program("", 1)
    with pytest.raises(ValueError):
        Program("P", -1)


def test_match_ranks_start_at_one() -> None:
    """Ranks below 1 are refused."""
    assert Match("A", "P", 1, 3).program_rank == 3
    with pytest.raises(ValueError):
        Match("A", "P", 0, 1)
    with pytest.raises(ValueError):
        Match("A", "P", 1, 0)


def test_dataclasses_are_frozen_and_slotted() -> None:
    """Instances cannot be mutated and carry no per-instance dict."""
    a = Applicant("A", 1)
    with pytest.raises(dataclasses.FrozenInstanceError):
        a.lottery = 2  # type: ignore[misc]
    assert not hasattr(a, "__dict__")


def test_validation_issue_string_includes_row() -> None:
    """The string form names the source and, when given, the row."""
    assert str(ValidationIssue("f.csv", "bad", row=4)) == "f.csv row 4: bad"
    assert str(ValidationIssue("Stability", "x")) == "Stability: x"


def test_generator_config_defaults_and_validation() -> None:
    """Defaults match the spec; invalid parameters raise UsageError."""
    cfg = GeneratorConfig(seed=1)
    assert (cfg.applicants, cfg.programs) == (20, 5)
    assert (cfg.capacity_min, cfg.capacity_max) == (2, 6)
    assert cfg.applicant_list_length == 5
    assert cfg.program_list_length is None
    with pytest.raises(UsageError):
        GeneratorConfig(seed=1, applicants=-1)
    with pytest.raises(UsageError):
        GeneratorConfig(seed=1, program_list_length=-2)
    with pytest.raises(UsageError):
        GeneratorConfig(seed=1, capacity_min=5, capacity_max=4)


def test_exit_codes_and_hierarchy() -> None:
    """InputError maps to 2, UsageError to 3, and both share the base class."""
    issues = [ValidationIssue("a.csv", "x", 1), ValidationIssue("b.csv", "y")]
    err = InputError(issues)
    assert err.exit_code == 2
    assert err.issues == tuple(issues)
    assert UsageError("bad").exit_code == 3
    assert isinstance(err, ResidencyMatchError)
    assert isinstance(UsageError("bad"), ResidencyMatchError)
