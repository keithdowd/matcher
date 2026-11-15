"""Shared test helpers: random markets, and an independent brute-force oracle.

The oracle enumerates every feasible matching and filters by the spec's blocking
pair definition. It deliberately shares no code with the production matcher or
the production StabilityCheck.
"""

from __future__ import annotations

import itertools

from hypothesis import strategies as st

from residency_match.market import Market
from residency_match.matching import Matching
from residency_match.models import Applicant, Program


def make_market(
    a_lists: dict[str, list[str]],
    p_lists: dict[str, list[str]],
    capacities: dict[str, int],
) -> Market:
    """Build a Market from plain dicts; lottery follows applicant order."""
    ids = list(a_lists)
    applicants = [Applicant(a, i + 1) for i, a in enumerate(ids)]
    programs = [Program(p, c) for p, c in capacities.items()]
    return Market(applicants, programs, a_lists, p_lists)


@st.composite
def markets(draw: st.DrawFn, max_applicants: int = 4, max_programs: int = 4) -> Market:
    """Hypothesis strategy for small random markets, including edge cases.

    Capacities may be zero, lists may be empty, and acceptability is partial.
    """
    n_a = draw(st.integers(0, max_applicants))
    n_p = draw(st.integers(0, max_programs))
    a_ids = [f"A{i}" for i in range(n_a)]
    p_ids = [f"P{i}" for i in range(n_p)]
    caps = {p: draw(st.integers(0, 3)) for p in p_ids}
    a_lists = {
        a: draw(st.lists(st.sampled_from(p_ids), unique=True)) if p_ids else []
        for a in a_ids
    }
    p_lists = {
        p: draw(st.lists(st.sampled_from(a_ids), unique=True)) if a_ids else []
        for p in p_ids
    }
    lottery = draw(st.permutations(range(1, n_a + 1)))
    applicants = [Applicant(a, lot) for a, lot in zip(a_ids, lottery, strict=True)]
    programs = [Program(p, caps[p]) for p in p_ids]
    return Market(applicants, programs, a_lists, p_lists)


def blocking_pairs(market: Market, matching: Matching) -> list[tuple[str, str]]:
    """Return every blocking pair, using the spec definition literally."""
    out: list[tuple[str, str]] = []
    for a in market.applicants:
        for p in market.programs:
            aid, pid = a.applicant_id, p.program_id
            a_rank = market.applicant_rank(aid, pid)
            p_rank = market.program_rank(pid, aid)
            if a_rank is None or p_rank is None:
                continue  # not acceptable
            cur = matching.program_of(aid)
            if cur is not None:
                cur_rank = market.applicant_rank(aid, cur)
                assert cur_rank is not None
                if not a_rank < cur_rank:
                    continue
            held = matching.holders(pid)
            if len(held) >= p.capacity:
                if not held:
                    continue  # capacity zero: no seat to block with
                worst = max(market.program_rank(pid, h) or 0 for h in held)
                if not p_rank < worst:
                    continue
            out.append((aid, pid))
    return out


def all_feasible_matchings(market: Market) -> list[Matching]:
    """Enumerate every matching using only acceptable pairs within capacity."""
    options = [
        [
            None,
            *[
                p
                for p in market.applicant_lists[a.applicant_id]
                if market.is_acceptable(a.applicant_id, p)
            ],
        ]
        for a in market.applicants
    ]
    result: list[Matching] = []
    for combo in itertools.product(*options):
        pairs = [
            (a.applicant_id, p)
            for a, p in zip(market.applicants, combo, strict=True)
            if p is not None
        ]
        counts: dict[str, int] = {}
        for _, p in pairs:
            counts[p] = counts.get(p, 0) + 1
        if all(c <= market.capacity(p) for p, c in counts.items()):
            result.append(Matching(pairs))
    return result


def stable_matchings(market: Market) -> list[Matching]:
    """Return every feasible matching with no blocking pair."""
    return [m for m in all_feasible_matchings(market) if not blocking_pairs(market, m)]


def applicant_rank_or_worst(market: Market, m: Matching, aid: str) -> int:
    """Rank of the applicant's outcome; unmatched is worse than any listed rank."""
    p = m.program_of(aid)
    if p is None:
        return 10**6
    rank = market.applicant_rank(aid, p)
    assert rank is not None
    return rank


def applicant_optimal(market: Market, candidates: list[Matching]) -> Matching | None:
    """Return the candidate every applicant weakly prefers, if one exists."""
    for m in candidates:
        if all(
            applicant_rank_or_worst(market, m, a.applicant_id)
            <= applicant_rank_or_worst(market, o, a.applicant_id)
            for a in market.applicants
            for o in candidates
        ):
            return m
    return None
