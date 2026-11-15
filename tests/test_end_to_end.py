"""End-to-end and property tests: random markets through the full pipeline."""

import tempfile
from datetime import datetime
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st
from rich.console import Console

from residency_match import cli
from residency_match.checks import Validator
from residency_match.generate import generate_files
from residency_match.io import CsvMarketLoader, CsvResultWriter, write_metadata
from residency_match.matching import DeferredAcceptance
from residency_match.models import GeneratorConfig
from tests.helpers import applicant_optimal, markets, stable_matchings

NOW = datetime(2026, 11, 15, 12, 0, 0)


@settings(max_examples=40, deadline=None)
@given(
    seed=st.integers(0, 2**32 - 1),
    applicants=st.integers(0, 40),
    programs=st.integers(0, 8),
    length=st.integers(0, 8),
    cap_min=st.integers(0, 3),
    cap_extra=st.integers(0, 4),
    program_length=st.one_of(st.none(), st.integers(0, 40)),
)
def test_generated_markets_pass_the_full_pipeline(
    seed: int,
    applicants: int,
    programs: int,
    length: int,
    cap_min: int,
    cap_extra: int,
    program_length: int | None,
) -> None:
    """Generate -> load -> match -> validate -> write never fails a check."""
    cfg = GeneratorConfig(
        seed=seed,
        applicants=applicants,
        programs=programs,
        capacity_min=cap_min,
        capacity_max=cap_min + cap_extra,
        applicant_list_length=length,
        program_list_length=program_length,
    )
    with tempfile.TemporaryDirectory() as tmp:
        data = Path(tmp) / "data"
        generate_files(cfg, data, NOW)
        market = CsvMarketLoader().load(data)
        matching = DeferredAcceptance(market).run()
        results = Validator.default().run(market, matching)
        assert all(r.passed for r in results), [
            i.detail for r in results for i in r.issues
        ]
        writer = CsvResultWriter(Path(tmp) / "out")
        writer.write_matches(market, matching)
        writer.write_program_summary(market, matching)
        writer.write_validation(results)
        assert (Path(tmp) / "out" / "matches.csv").read_text(encoding="utf-8").count(
            "\n"
        ) == applicants + 1


@settings(max_examples=20, deadline=None)
@given(st.integers(0, 2**32 - 1))
def test_cli_pipeline_exits_zero_for_any_seed(seed: int) -> None:
    """The real commands succeed in-process for arbitrary seeds."""
    with tempfile.TemporaryDirectory() as tmp:
        console = Console(record=True, force_terminal=False)
        data, out = Path(tmp) / "d", Path(tmp) / "r"
        gen = ["generate", "--seed", str(seed), "--out", str(data), "--quiet"]
        assert cli.main(gen, console=console, interactive=False) == 0
        match = ["match", "--input", str(data), "--out", str(out), "--quiet"]
        assert cli.main(match, console=console, interactive=False) == 0


def test_same_seed_gives_identical_matches(tmp_path: Path) -> None:
    """Two full runs from one seed write identical match files."""
    outputs = []
    for name in ("one", "two"):
        data, out = tmp_path / name / "d", tmp_path / name / "r"
        cfg = GeneratorConfig(seed=99)
        generate_files(cfg, data, NOW)
        market = CsvMarketLoader().load(data)
        matching = DeferredAcceptance(market).run()
        CsvResultWriter(out).write_matches(market, matching)
        outputs.append((out / "matches.csv").read_bytes())
    assert outputs[0] == outputs[1]


def test_target_scale_run_fills_sensibly() -> None:
    """At the target scale (20 applicants, 5 programs) the run is valid."""
    with tempfile.TemporaryDirectory() as tmp:
        generate_files(GeneratorConfig(seed=42), Path(tmp), NOW)
        market = CsvMarketLoader().load(Path(tmp))
    matching = DeferredAcceptance(market).run()
    assert len(matching.pairs) <= sum(p.capacity for p in market.programs)
    assert all(r.passed for r in Validator.default().run(market, matching))


def test_larger_market_is_stable() -> None:
    """A market 10x the target scale still passes every check."""
    with tempfile.TemporaryDirectory() as tmp:
        cfg = GeneratorConfig(seed=5, applicants=200, programs=20, capacity_max=15)
        generate_files(cfg, Path(tmp), NOW)
        market = CsvMarketLoader().load(Path(tmp))
    matching = DeferredAcceptance(market).run()
    assert all(r.passed for r in Validator.default().run(market, matching))


def test_metadata_seed_flows_from_generate_to_match(tmp_path: Path) -> None:
    """The match metadata copies the seed recorded by generate."""
    console = Console(record=True, force_terminal=False)
    data, out = tmp_path / "d", tmp_path / "r"
    cli.main(
        ["generate", "--seed", "123", "--out", str(data)],
        console=console,
        interactive=False,
    )
    cli.main(
        ["match", "--input", str(data), "--out", str(out)],
        console=console,
        interactive=False,
    )
    assert '"seed": 123' in (out / "run_metadata.json").read_text(encoding="utf-8")
    # And when the input has no metadata the seed is null.
    (data / "run_metadata.json").unlink()
    cli.main(
        ["match", "--input", str(data), "--out", str(out)],
        console=console,
        interactive=False,
    )
    assert '"seed": null' in (out / "run_metadata.json").read_text(encoding="utf-8")
    write_metadata(tmp_path, {})  # helper stays importable from the public API


@settings(max_examples=100, deadline=None)
@given(markets())
def test_oracle_agrees_on_random_markets(market) -> None:  # type: ignore[no-untyped-def]
    """Brute force and DA agree end to end, with every validator check passing."""
    matching = DeferredAcceptance(market).run()
    assert applicant_optimal(market, stable_matchings(market)) == matching
    assert all(r.passed for r in Validator.default().run(market, matching))
