"""Seeded mock data generator.

All randomness comes from one injected NumPy generator, so the same seed always
produces the same market. The uniform draws are a placeholder for a future
generative model of realistic rankings. This module does not read arguments or
print anything; ``cli.py`` and ``console.py`` handle that.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import numpy as np

from residency_match.io import (
    CsvMarketLoader,
    CsvMarketWriter,
    environment_versions,
    write_metadata,
)
from residency_match.market import Market
from residency_match.models import Applicant, GeneratorConfig, Program


def _width(count: int, minimum: int) -> int:
    """Return the digit width needed so ids sort in numeric order."""
    return max(minimum, len(str(count)))


class MockGenerator:
    """Builds a random :class:`Market` from a configuration.

    Parameters
    ----------
    rng : numpy.random.Generator
        Source of every random draw. Inject ``numpy.random.default_rng(seed)``
        for reproducible output.

    Examples
    --------
    >>> cfg = GeneratorConfig(seed=1, applicants=4, programs=2, applicant_list_length=2)
    >>> market = MockGenerator(np.random.default_rng(cfg.seed)).generate(cfg)
    >>> len(market.applicants), len(market.programs)
    (4, 2)
    """

    def __init__(self, rng: np.random.Generator) -> None:
        """Store the random generator."""
        self._rng = rng

    @staticmethod
    def effective_lengths(config: GeneratorConfig) -> tuple[int, int]:
        """Clamp list lengths to what is available.

        Parameters
        ----------
        config : GeneratorConfig
            Requested parameters.

        Returns
        -------
        tuple of int
            ``(applicant_list_length, program_list_length)`` after clamping to
            the number of programs and applicants respectively. A program list
            length of ``None`` means every applicant.
        """
        a_len = min(config.applicant_list_length, config.programs)
        p_req = (
            config.applicants
            if config.program_list_length is None
            else (config.program_list_length)
        )
        return a_len, min(p_req, config.applicants)

    def generate(self, config: GeneratorConfig) -> Market:
        """Draw a market.

        The order of draws is fixed (capacities, lottery, applicant lists,
        program lists) because reproducibility depends on it.

        Parameters
        ----------
        config : GeneratorConfig
            What to generate.

        Returns
        -------
        Market
            Applicants ``A001..``, programs ``P01..``, strict rankings.
        """
        rng = self._rng
        a_len, p_len = self.effective_lengths(config)
        a_w = _width(config.applicants, 3)
        p_w = _width(config.programs, 2)
        a_ids = [f"A{i:0{a_w}d}" for i in range(1, config.applicants + 1)]
        p_ids = [f"P{i:0{p_w}d}" for i in range(1, config.programs + 1)]

        capacities = rng.integers(
            config.capacity_min, config.capacity_max + 1, size=config.programs
        )
        # A permutation of 1..n so no two applicants tie on the lottery.
        lottery = rng.permutation(config.applicants) + 1

        # Each list is the head of a fresh random permutation, which is a random
        # sample in random order.
        a_lists = {
            a: [p_ids[j] for j in rng.permutation(config.programs)[:a_len]]
            for a in a_ids
        }
        p_lists = {
            p: [a_ids[j] for j in rng.permutation(config.applicants)[:p_len]]
            for p in p_ids
        }
        return Market(
            [Applicant(a, int(n)) for a, n in zip(a_ids, lottery, strict=True)],
            [Program(p, int(c)) for p, c in zip(p_ids, capacities, strict=True)],
            a_lists,
            p_lists,
        )


def generate_files(config: GeneratorConfig, directory: Path, now: datetime) -> Market:
    """Generate a market, write it, validate the files, then write metadata.

    The files are loaded back with the same loader the match command uses
    before the metadata file is written, so a generator bug fails here.

    Parameters
    ----------
    config : GeneratorConfig
        What to generate.
    directory : Path
        Output directory; created if needed.
    now : datetime
        Timestamp to record in the metadata.

    Returns
    -------
    Market
        The generated market.

    Raises
    ------
    InputError
        If the written files fail input validation (a generator bug).
    """
    market = MockGenerator(np.random.default_rng(config.seed)).generate(config)
    CsvMarketWriter().write(market, directory)
    CsvMarketLoader().load(directory)
    a_len, p_len = MockGenerator.effective_lengths(config)
    write_metadata(
        directory,
        {
            "seed": config.seed,
            "parameters": asdict(config),
            "effective": {
                "applicant_list_length": a_len,
                "program_list_length": p_len,
            },
            "timestamp": now.isoformat(timespec="seconds"),
            "versions": environment_versions(),
        },
    )
    return market
