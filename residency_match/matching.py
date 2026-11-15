"""Matching results and the resident-proposing deferred acceptance algorithm.

This module has no file or console I/O. Progress is reported through an optional
callback so the console layer can show it without this module knowing about it.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from residency_match.market import Market
from residency_match.models import Match


@dataclass(frozen=True, slots=True)
class Matching:
    """Immutable result: which program, if any, holds each applicant.

    Parameters
    ----------
    pairs : Iterable[tuple[str, str]]
        ``(applicant_id, program_id)`` pairs. Each applicant may appear at
        most once in a valid matching; applicants left out are unmatched.

    Attributes
    ----------
    pairs : tuple[tuple[str, str], ...]
        The pairs sorted by applicant id. Two matchings are equal exactly when
        their pairs are equal.

    Notes
    -----
    Duplicate applicants are deliberately *not* rejected here, so that the
    validator's single-match check can detect them independently of the
    algorithm. ``program_of`` returns the first pair in sorted order.

    Examples
    --------
    >>> m = Matching([("A", "P"), ("B", "P")])
    >>> m.program_of("A"), m.program_of("Z")
    ('P', None)
    >>> m.holders("P")
    ('A', 'B')
    """

    pairs: tuple[tuple[str, str], ...]
    _program_of: Mapping[str, str] = field(init=False, repr=False, compare=False)
    _holders: Mapping[str, tuple[str, ...]] = field(
        init=False, repr=False, compare=False
    )

    def __init__(self, pairs: Iterable[tuple[str, str]]) -> None:
        """Sort the pairs and build lookups in both directions."""
        ordered = tuple(sorted(pairs))
        program_of: dict[str, str] = {}
        for applicant_id, program_id in ordered:
            program_of.setdefault(applicant_id, program_id)
        holders: dict[str, list[str]] = {}
        for applicant_id, program_id in ordered:
            holders.setdefault(program_id, []).append(applicant_id)
        object.__setattr__(self, "pairs", ordered)
        object.__setattr__(self, "_program_of", MappingProxyType(program_of))
        object.__setattr__(
            self,
            "_holders",
            MappingProxyType({p: tuple(v) for p, v in holders.items()}),
        )

    def program_of(self, applicant_id: str) -> str | None:
        """Return the program holding an applicant.

        Parameters
        ----------
        applicant_id : str
            Any applicant id.

        Returns
        -------
        str or None
            The program id, or ``None`` if the applicant is unmatched.
        """
        return self._program_of.get(applicant_id)

    def holders(self, program_id: str) -> tuple[str, ...]:
        """Return the applicants a program holds.

        Parameters
        ----------
        program_id : str
            Any program id.

        Returns
        -------
        tuple of str
            Applicant ids sorted by id; empty if the program holds none.
        """
        return self._holders.get(program_id, ())

    def to_matches(self, market: Market) -> list[Match]:
        """Attach each side's rank of the other to every pair.

        Parameters
        ----------
        market : Market
            The market this matching was computed on.

        Returns
        -------
        list of Match
            One entry per matched applicant, sorted by applicant id.

        Raises
        ------
        ValueError
            If a pair is not acceptable in ``market``.
        """
        out: list[Match] = []
        for applicant_id, program_id in self.pairs:
            a_rank = market.applicant_rank(applicant_id, program_id)
            p_rank = market.program_rank(program_id, applicant_id)
            if a_rank is None or p_rank is None:
                raise ValueError(f"pair {applicant_id}-{program_id} is not listed")
            out.append(Match(applicant_id, program_id, a_rank, p_rank))
        return out


class DeferredAcceptance:
    """Resident-proposing deferred acceptance (Gale-Shapley).

    Produces the applicant-optimal stable matching. The instance keeps private
    mutable state for one run; create a new instance for each run.

    Parameters
    ----------
    market : Market
        The problem to solve.

    Examples
    --------
    >>> from residency_match.models import Applicant, Program
    >>> m = Market([Applicant("A", 1)], [Program("P", 1)], {"A": ["P"]}, {"P": ["A"]})
    >>> DeferredAcceptance(m).run().program_of("A")
    'P'
    """

    def __init__(self, market: Market) -> None:
        """Set up empty holds and pointers at the head of every list."""
        self._market = market
        # Index of the next program each applicant will propose to.
        self._pointer: dict[str, int] = {a.applicant_id: 0 for a in market.applicants}
        # Applicants each program is currently holding (never over capacity).
        self._held: dict[str, list[str]] = {p.program_id: [] for p in market.programs}
        # Applicant -> program currently holding them; absent when unmatched.
        self._holding: dict[str, str] = {}

    def run(self, on_round: Callable[[int, int], None] | None = None) -> Matching:
        """Run to completion.

        Parameters
        ----------
        on_round : callable, optional
            Called after each round with ``(round_number, proposals_made)``.

        Returns
        -------
        Matching
            The applicant-optimal stable matching.
        """
        market = self._market
        round_no = 0
        while True:
            # Every unmatched applicant with programs left proposes to the
            # program at their pointer. Iterating in market order keeps the
            # run deterministic.
            proposals: dict[str, list[str]] = {}
            for a in market.applicants:
                aid = a.applicant_id
                if aid in self._holding:
                    continue
                lst = market.applicant_lists[aid]
                if self._pointer[aid] < len(lst):
                    proposals.setdefault(lst[self._pointer[aid]], []).append(aid)
            if not proposals:
                break
            round_no += 1
            for program_id, proposers in proposals.items():
                self._consider(program_id, proposers)
            if on_round is not None:
                on_round(round_no, sum(len(v) for v in proposals.values()))
        return Matching((aid, pid) for aid, pid in self._holding.items())

    def _consider(self, program_id: str, proposers: list[str]) -> None:
        """Let one program keep its best applicants from holds plus proposers.

        Deferred acceptance means a hold is only tentative: a program may drop
        a held applicant when better ones propose. Rejected applicants advance
        their pointer so each pair is proposed at most once.
        """
        market = self._market
        capacity = market.capacity(program_id)
        pool = self._held[program_id] + proposers
        # An applicant the program does not rank is unacceptable and is always
        # rejected, whatever the capacity.
        ranked = [a for a in pool if market.program_rank(program_id, a) is not None]

        def priority(aid: str) -> tuple[int, int]:
            # Lower sorts first. Version 1 rankings are strict, so the rank
            # alone decides; the lottery is the fixed tie-break (lower number
            # ranks higher) that a future tied-score input would reach.
            rank = market.program_rank(program_id, aid)
            assert rank is not None
            return (rank, market.lottery(aid))

        ranked.sort(key=priority)
        kept = ranked[:capacity]
        kept_set = set(kept)
        for aid in pool:
            if aid in kept_set:
                self._holding[aid] = program_id
            else:
                # Rejected (new proposer or dropped hold): move to next program.
                self._holding.pop(aid, None)
                self._pointer[aid] += 1
        self._held[program_id] = kept
