"""Tests for the seeded mock data generator."""

import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from residency_match.checks import Validator
from residency_match.generate import MockGenerator, generate_files
from residency_match.io import CsvMarketLoader, read_seed
from residency_match.matching import DeferredAcceptance
from residency_match.models import GeneratorConfig

NOW = datetime(2026, 11, 15, 12, 0, 0)


def _gen(**kw: int) -> GeneratorConfig:
    """Build a config with a default seed of 7 and overrides."""
    kw.setdefault("seed", 7)
    return GeneratorConfig(**kw)


def test_defaults_match_the_spec() -> None:
    """Default run: 20 applicants, 5 programs, 5-long lists, capacity 2-6."""
    cfg = _gen()
    market = MockGenerator(np.random.default_rng(cfg.seed)).generate(cfg)
    assert len(market.applicants) == 20
    assert len(market.programs) == 5
    assert all(2 <= p.capacity <= 6 for p in market.programs)
    assert all(len(v) == 5 for v in market.applicant_lists.values())
    assert all(len(v) == 20 for v in market.program_lists.values())
    assert sorted(a.lottery for a in market.applicants) == list(range(1, 21))


def test_same_seed_same_market_different_seed_differs() -> None:
    """The seed alone fixes the market."""
    cfg = _gen()
    one = MockGenerator(np.random.default_rng(7)).generate(cfg)
    two = MockGenerator(np.random.default_rng(7)).generate(cfg)
    other = MockGenerator(np.random.default_rng(8)).generate(cfg)
    assert one == two
    assert one != other


def test_list_lengths_are_clamped() -> None:
    """Requested lengths above what exists are clamped, not errors."""
    cfg = _gen(applicants=4, programs=2, applicant_list_length=9)
    cfg2 = GeneratorConfig(
        seed=1,
        applicants=4,
        programs=2,
        applicant_list_length=9,
        program_list_length=99,
    )
    assert MockGenerator.effective_lengths(cfg) == (2, 4)
    assert MockGenerator.effective_lengths(cfg2) == (2, 4)
    market = MockGenerator(np.random.default_rng(1)).generate(cfg2)
    assert all(len(v) == 2 for v in market.applicant_lists.values())


def test_partial_program_lists() -> None:
    """A program list length below the applicant count ranks only some."""
    cfg = GeneratorConfig(seed=3, applicants=10, programs=3, program_list_length=4)
    market = MockGenerator(np.random.default_rng(3)).generate(cfg)
    assert all(len(v) == 4 for v in market.program_lists.values())


def test_empty_market_generates() -> None:
    """Zero applicants or zero programs is valid."""
    for cfg in (_gen(applicants=0), _gen(programs=0)):
        MockGenerator(np.random.default_rng(1)).generate(cfg)


def test_files_are_identical_for_the_same_seed(tmp_path: Path) -> None:
    """Two runs with one seed write byte-identical input files."""
    generate_files(_gen(), tmp_path / "a", NOW)
    generate_files(_gen(), tmp_path / "b", NOW)
    for name in (
        "applicants.csv",
        "programs.csv",
        "applicant_rankings.csv",
        "program_rankings.csv",
        "run_metadata.json",
    ):
        assert (tmp_path / "a" / name).read_bytes() == (
            tmp_path / "b" / name
        ).read_bytes()


def test_generated_files_load_and_validate(tmp_path: Path) -> None:
    """Generated output passes the loader and the full validator."""
    market = generate_files(_gen(seed=42), tmp_path, NOW)
    loaded = CsvMarketLoader().load(tmp_path)
    assert loaded == market
    matching = DeferredAcceptance(loaded).run()
    assert all(r.passed for r in Validator.default().run(loaded, matching))


def test_metadata_records_seed_and_parameters(tmp_path: Path) -> None:
    """The metadata file has the seed, parameters, effective lengths, versions."""
    generate_files(_gen(seed=42, programs=2), tmp_path, NOW)
    data = json.loads((tmp_path / "run_metadata.json").read_text(encoding="utf-8"))
    assert data["seed"] == 42
    assert data["parameters"]["programs"] == 2
    assert data["effective"] == {"applicant_list_length": 2, "program_list_length": 20}
    assert data["timestamp"] == "2026-11-15T12:00:00"
    assert set(data["versions"]) == {"python", "numpy", "pandas"}
    assert read_seed(tmp_path) == 42


def test_generator_config_errors_surface() -> None:
    """Invalid parameters are rejected before any draw happens."""
    with pytest.raises(Exception):  # noqa: B017 - UsageError, asserted in test_models
        _gen(applicants=-1)


@settings(max_examples=60, deadline=None)
@given(
    seed=st.integers(0, 2**32 - 1),
    applicants=st.integers(0, 12),
    programs=st.integers(0, 5),
    length=st.integers(0, 7),
)
def test_any_config_round_trips_through_files(
    seed: int, applicants: int, programs: int, length: int
) -> None:
    """Any valid config writes files the loader accepts (property test)."""
    import tempfile

    cfg = GeneratorConfig(
        seed=seed,
        applicants=applicants,
        programs=programs,
        applicant_list_length=length,
    )
    with tempfile.TemporaryDirectory() as tmp:
        market = generate_files(cfg, Path(tmp), NOW)
        assert CsvMarketLoader().load(Path(tmp)) == market
