"""Frozen dataclasses that hold the data of the residency match simulator.

Each class validates its own invariants on construction. This module does no file
or console I/O and contains no matching logic.
"""

from __future__ import annotations

from dataclasses import dataclass

from residency_match.errors import UsageError


@dataclass(frozen=True, slots=True)
class Applicant:
    """One applicant.

    Attributes
    ----------
    applicant_id : str
        Non-empty identifier, unique within a market.
    lottery : int
        Number drawn once per applicant and used for every tie. A lower number
        ranks higher.

    Raises
    ------
    ValueError
        If ``applicant_id`` is empty.
    """

    applicant_id: str
    lottery: int

    def __post_init__(self) -> None:
        """Check the invariants."""
        if not self.applicant_id:
            raise ValueError("applicant_id must be non-empty")


@dataclass(frozen=True, slots=True)
class Program:
    """One program.

    Attributes
    ----------
    program_id : str
        Non-empty identifier, unique within a market.
    capacity : int
        Number of seats. Zero is allowed.

    Raises
    ------
    ValueError
        If ``program_id`` is empty or ``capacity`` is negative.
    """

    program_id: str
    capacity: int

    def __post_init__(self) -> None:
        """Check the invariants."""
        if not self.program_id:
            raise ValueError("program_id must be non-empty")
        if self.capacity < 0:
            raise ValueError("capacity must be non-negative")


@dataclass(frozen=True, slots=True)
class Match:
    """One matched applicant-program pair with each side's rank of the other.

    Attributes
    ----------
    applicant_id : str
        The matched applicant.
    program_id : str
        The program holding the applicant.
    applicant_rank : int
        Position of the program on the applicant's list; 1 is most preferred.
    program_rank : int
        Position of the applicant on the program's list; 1 is most preferred.

    Raises
    ------
    ValueError
        If either rank is below 1.
    """

    applicant_id: str
    program_id: str
    applicant_rank: int
    program_rank: int

    def __post_init__(self) -> None:
        """Check the invariants."""
        if self.applicant_rank < 1 or self.program_rank < 1:
            raise ValueError("ranks start at 1")


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """One problem found by an input check or a validation check.

    Attributes
    ----------
    source : str
        Where the problem was found: a file name for input problems, or a check
        name such as ``"Stability"`` for validation problems.
    detail : str
        Human-readable description.
    row : int or None
        One-based data row number in the file (header excluded), if relevant.
    """

    source: str
    detail: str
    row: int | None = None

    def __str__(self) -> str:
        """Format as ``source[ row N]: detail``."""
        where = f" row {self.row}" if self.row is not None else ""
        return f"{self.source}{where}: {self.detail}"


@dataclass(frozen=True, slots=True)
class GeneratorConfig:
    """Parameters of the mock data generator.

    Attributes
    ----------
    seed : int
        Fixes every random draw.
    applicants : int
        Number of applicants.
    programs : int
        Number of programs.
    capacity_min, capacity_max : int
        Each program's capacity is drawn uniformly from this inclusive range.
    applicant_list_length : int
        Programs each applicant ranks; clamped to ``programs`` by the generator.
    program_list_length : int or None
        Applicants each program ranks; ``None`` means all, and larger values are
        clamped to ``applicants`` by the generator.

    Raises
    ------
    UsageError
        If a count is negative or ``capacity_max < capacity_min``.
    """

    seed: int
    applicants: int = 20
    programs: int = 5
    capacity_min: int = 2
    capacity_max: int = 6
    applicant_list_length: int = 5
    program_list_length: int | None = None

    def __post_init__(self) -> None:
        """Check the invariants."""
        counts = {
            "applicants": self.applicants,
            "programs": self.programs,
            "capacity_min": self.capacity_min,
            "applicant_list_length": self.applicant_list_length,
        }
        if self.program_list_length is not None:
            counts["program_list_length"] = self.program_list_length
        for name, value in counts.items():
            if value < 0:
                raise UsageError(f"{name} must be non-negative")
        if self.capacity_max < self.capacity_min:
            raise UsageError("capacity_max must be at least capacity_min")
