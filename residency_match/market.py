"""Immutable definition of one matching problem.

A :class:`Market` bundles applicants, programs and both sides' rankings, and
precomputes rank lookups. It performs no file or console I/O and runs no
matching; that is the job of ``matching.py``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType

from residency_match.models import Applicant, Program


@dataclass(frozen=True, slots=True)
class Market:
    """Applicants, programs, and both sides' ranked lists.

    Rank convention: positions are 1-based and 1 is most preferred. A pair is
    *acceptable* only when each side lists the other; unlisted pairs are
    unacceptable on both sides.

    Parameters
    ----------
    applicants : Sequence[Applicant]
        All applicants; ids must be unique.
    programs : Sequence[Program]
        All programs; ids must be unique.
    applicant_lists : Mapping[str, Sequence[str]]
        For each applicant id, program ids from most to least preferred.
        Applicants missing from the mapping have an empty list.
    program_lists : Mapping[str, Sequence[str]]
        For each program id, applicant ids from most to least preferred.
        Programs missing from the mapping rank nobody.

    Attributes
    ----------
    applicants, programs : tuple
        The inputs, in the order given. That order is the deterministic
        iteration order used by the matcher.
    applicant_lists, program_lists : Mapping[str, tuple[str, ...]]
        Read-only copies of the ranked lists.

    Raises
    ------
    ValueError
        If ids are duplicated, a list names an unknown id, or a list repeats
        an entry.

    Examples
    --------
    >>> m = Market(
    ...     [Applicant("A", 1)], [Program("P", 1)], {"A": ["P"]}, {"P": ["A"]}
    ... )
    >>> m.is_acceptable("A", "P")
    True
    >>> m.applicant_rank("A", "P")
    1
    """

    applicants: tuple[Applicant, ...]
    programs: tuple[Program, ...]
    applicant_lists: Mapping[str, tuple[str, ...]]
    program_lists: Mapping[str, tuple[str, ...]]
    # Derived lookups, built once in __post_init__ and excluded from equality.
    _applicant_ranks: Mapping[str, Mapping[str, int]] = field(
        init=False, repr=False, compare=False
    )
    _program_ranks: Mapping[str, Mapping[str, int]] = field(
        init=False, repr=False, compare=False
    )
    _lottery: Mapping[str, int] = field(init=False, repr=False, compare=False)
    _capacity: Mapping[str, int] = field(init=False, repr=False, compare=False)

    def __init__(
        self,
        applicants: Sequence[Applicant],
        programs: Sequence[Program],
        applicant_lists: Mapping[str, Sequence[str]],
        program_lists: Mapping[str, Sequence[str]],
    ) -> None:
        """Validate the inputs and build the immutable lookups."""
        a_ids = [a.applicant_id for a in applicants]
        p_ids = [p.program_id for p in programs]
        if len(set(a_ids)) != len(a_ids):
            raise ValueError("duplicate applicant_id")
        if len(set(p_ids)) != len(p_ids):
            raise ValueError("duplicate program_id")
        a_set, p_set = set(a_ids), set(p_ids)

        a_lists = {a: tuple(applicant_lists.get(a, ())) for a in a_ids}
        p_lists = {p: tuple(program_lists.get(p, ())) for p in p_ids}
        if not set(applicant_lists) <= a_set or not set(program_lists) <= p_set:
            raise ValueError("ranked list for an unknown id")
        for lst, known in [(v, p_set) for v in a_lists.values()] + [
            (v, a_set) for v in p_lists.values()
        ]:
            if not set(lst) <= known:
                raise ValueError("list names an unknown id")
            if len(set(lst)) != len(lst):
                raise ValueError("list repeats an entry")

        set_ = object.__setattr__
        set_(self, "applicants", tuple(applicants))
        set_(self, "programs", tuple(programs))
        set_(self, "applicant_lists", MappingProxyType(a_lists))
        set_(self, "program_lists", MappingProxyType(p_lists))
        set_(
            self,
            "_applicant_ranks",
            MappingProxyType(
                {a: {p: i for i, p in enumerate(v, 1)} for a, v in a_lists.items()}
            ),
        )
        set_(
            self,
            "_program_ranks",
            MappingProxyType(
                {p: {a: i for i, a in enumerate(v, 1)} for p, v in p_lists.items()}
            ),
        )
        set_(self, "_lottery", {a.applicant_id: a.lottery for a in applicants})
        set_(self, "_capacity", {p.program_id: p.capacity for p in programs})

    def capacity(self, program_id: str) -> int:
        """Return the seat count of a program.

        Parameters
        ----------
        program_id : str
            A program in this market.

        Returns
        -------
        int
            Number of seats.
        """
        return self._capacity[program_id]

    def lottery(self, applicant_id: str) -> int:
        """Return an applicant's lottery number (lower ranks higher in ties).

        Parameters
        ----------
        applicant_id : str
            An applicant in this market.

        Returns
        -------
        int
            The lottery number.
        """
        return self._lottery[applicant_id]

    def applicant_rank(self, applicant_id: str, program_id: str) -> int | None:
        """Return the 1-based position of a program on an applicant's list.

        Parameters
        ----------
        applicant_id : str
            An applicant in this market.
        program_id : str
            Any program id.

        Returns
        -------
        int or None
            The rank, or ``None`` if the applicant does not list the program.
        """
        return self._applicant_ranks[applicant_id].get(program_id)

    def program_rank(self, program_id: str, applicant_id: str) -> int | None:
        """Return the 1-based position of an applicant on a program's list.

        Parameters
        ----------
        program_id : str
            A program in this market.
        applicant_id : str
            Any applicant id.

        Returns
        -------
        int or None
            The rank, or ``None`` if the program does not rank the applicant.
        """
        return self._program_ranks[program_id].get(applicant_id)

    def is_acceptable(self, applicant_id: str, program_id: str) -> bool:
        """Test whether both sides list each other.

        Parameters
        ----------
        applicant_id : str
            An applicant in this market.
        program_id : str
            A program in this market.

        Returns
        -------
        bool
            ``True`` only if the applicant lists the program and the program
            ranks the applicant.
        """
        return (
            self.applicant_rank(applicant_id, program_id) is not None
            and self.program_rank(program_id, applicant_id) is not None
        )

    def acceptable_pairs(self) -> list[tuple[str, str]]:
        """List every acceptable (applicant_id, program_id) pair.

        Returns
        -------
        list of tuple of str
            Pairs in applicant order, then the applicant's list order.
        """
        return [
            (a.applicant_id, p)
            for a in self.applicants
            for p in self.applicant_lists[a.applicant_id]
            if self.is_acceptable(a.applicant_id, p)
        ]
