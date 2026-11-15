"""Validation checks run after every match, and the validator that runs them.

Each check inspects a finished :class:`Matching` against its :class:`Market` and
returns the problems it finds. This module does no file or console I/O, and the
checks do not share logic with the matcher (except the reproducibility check,
whose whole point is to run the matcher again).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from residency_match.market import Market
from residency_match.matching import DeferredAcceptance, Matching
from residency_match.models import ValidationIssue


class Check(Protocol):
    """Interface every validation check implements.

    Attributes
    ----------
    name : str
        Check name as it appears in ``validation.csv``.
    """

    name: str

    def run(self, market: Market, matching: Matching) -> list[ValidationIssue]:
        """Run the check.

        Parameters
        ----------
        market : Market
            The problem that was solved.
        matching : Matching
            The result to inspect.

        Returns
        -------
        list of ValidationIssue
            One issue per problem found; empty means the check passed.
        """
        ...


@dataclass(frozen=True, slots=True)
class CheckResult:
    """Outcome of one check.

    Attributes
    ----------
    check : str
        The check name.
    issues : tuple[ValidationIssue, ...]
        Problems found; empty means PASS.
    """

    check: str
    issues: tuple[ValidationIssue, ...]

    @property
    def passed(self) -> bool:
        """Whether the check found no problems."""
        return not self.issues


class CapacityCheck:
    """Passes when no program holds more applicants than its capacity."""

    name = "Capacity"

    def run(self, market: Market, matching: Matching) -> list[ValidationIssue]:
        """Report each program held over capacity."""
        known = {p.program_id for p in market.programs}
        counts = Counter(p for _, p in matching.pairs if p in known)
        return [
            ValidationIssue(
                self.name,
                f"program {pid} holds {n} applicants, capacity {market.capacity(pid)}",
            )
            for pid, n in sorted(counts.items())
            if n > market.capacity(pid)
        ]


class SingleMatchCheck:
    """Passes when each applicant appears in at most one match."""

    name = "Single match"

    def run(self, market: Market, matching: Matching) -> list[ValidationIssue]:
        """Report each applicant that appears more than once."""
        counts = Counter(a for a, _ in matching.pairs)
        return [
            ValidationIssue(self.name, f"applicant {aid} appears {n} times")
            for aid, n in sorted(counts.items())
            if n > 1
        ]


class ListedPairsCheck:
    """Passes when every match is a pair that both sides list."""

    name = "Listed pairs only"

    def run(self, market: Market, matching: Matching) -> list[ValidationIssue]:
        """Report each matched pair that is not acceptable."""
        known_a = set(market.applicant_lists)
        known_p = set(market.program_lists)
        return [
            ValidationIssue(
                self.name, f"applicant {aid} and program {pid} not both listed"
            )
            for aid, pid in matching.pairs
            if aid not in known_a
            or pid not in known_p
            or not market.is_acceptable(aid, pid)
        ]


class StabilityCheck:
    """Passes when no blocking pair exists.

    Tests every acceptable pair, so cost is quadratic in the number of pairs in
    the worst case; fast at the target scale.
    """

    name = "Stability"

    def run(self, market: Market, matching: Matching) -> list[ValidationIssue]:
        """Report each blocking pair.

        A pair blocks when it is acceptable, the applicant is unmatched or
        prefers the program to their current one, and the program has a free
        seat or prefers the applicant to its worst held applicant.
        """
        issues: list[ValidationIssue] = []
        for aid, pid in market.acceptable_pairs():
            a_rank = market.applicant_rank(aid, pid)
            p_rank = market.program_rank(pid, aid)
            assert a_rank is not None and p_rank is not None  # acceptable
            current = matching.program_of(aid)
            if current is not None:
                current_rank = market.applicant_rank(aid, current)
                # A current match outside the applicant's list is never better.
                if current_rank is not None and a_rank >= current_rank:
                    continue
            held = matching.holders(pid)
            if len(held) >= market.capacity(pid):
                # Full (or zero-capacity): only displacing someone can help.
                ranks = [market.program_rank(pid, h) for h in held]
                worst = max((r for r in ranks if r is not None), default=None)
                if worst is None or p_rank >= worst:
                    continue
            issues.append(
                ValidationIssue(
                    self.name, f"blocking pair: applicant {aid}, program {pid}"
                )
            )
        return issues


class ReproducibilityCheck:
    """Passes when re-running the matcher on the same market gives the same result."""

    name = "Reproducibility"

    def run(self, market: Market, matching: Matching) -> list[ValidationIssue]:
        """Run deferred acceptance again and compare with ``matching``."""
        again = DeferredAcceptance(market).run()
        if again == matching:
            return []
        return [
            ValidationIssue(self.name, "a second run produced a different matching")
        ]


class Validator:
    """Runs an ordered list of checks and collects their results.

    Parameters
    ----------
    checks : Sequence[Check]
        Checks to run, in order.

    Examples
    --------
    >>> Validator.default().checks[0].name
    'Capacity'
    """

    def __init__(self, checks: Sequence[Check]) -> None:
        """Store the checks."""
        self.checks: tuple[Check, ...] = tuple(checks)

    @classmethod
    def default(cls) -> Validator:
        """Build the standard validator with all five checks, in spec order.

        Returns
        -------
        Validator
            Capacity, single match, listed pairs, stability, reproducibility.
        """
        return cls(
            [
                CapacityCheck(),
                SingleMatchCheck(),
                ListedPairsCheck(),
                StabilityCheck(),
                ReproducibilityCheck(),
            ]
        )

    def run(self, market: Market, matching: Matching) -> list[CheckResult]:
        """Run every check.

        Parameters
        ----------
        market : Market
            The problem that was solved.
        matching : Matching
            The result to validate.

        Returns
        -------
        list of CheckResult
            One result per check, in order.
        """
        return [
            CheckResult(c.name, tuple(c.run(market, matching))) for c in self.checks
        ]
