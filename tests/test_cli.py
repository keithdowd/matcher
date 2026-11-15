"""Tests for the command-line interface: exit codes, prompts and overwrite rule."""

import subprocess
import sys
from pathlib import Path

import pytest
from rich.console import Console

from residency_match import cli
from residency_match.matching import Matching


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    """Run the program in a subprocess with piped (non-terminal) stdio."""
    return subprocess.run(
        [sys.executable, "-m", "residency_match", *args],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        check=False,
    )


def _generate(tmp_path: Path) -> Path:
    """Generate a small data set and return its directory."""
    data = tmp_path / "data"
    done = _run("generate", "--seed", "42", "--out", str(data))
    assert done.returncode == 0, done.stderr
    return data


def test_exit_0_generate_and_match(tmp_path: Path) -> None:
    """Generate then match succeed with status 0 and write every output."""
    data = _generate(tmp_path)
    assert (data / "run_metadata.json").is_file()
    out = tmp_path / "results"
    done = _run("match", "--input", str(data), "--out", str(out))
    assert done.returncode == 0, done.stderr
    for name in (
        "matches.csv",
        "program_summary.csv",
        "validation.csv",
        "run_metadata.json",
    ):
        assert (out / name).is_file()
    assert "Seed: 42" in done.stdout
    assert "Exit status: 0" in done.stdout


def test_exit_2_input_error_writes_nothing(tmp_path: Path) -> None:
    """Bad input gives status 2, names file and row, and writes no outputs."""
    data = _generate(tmp_path)
    (data / "programs.csv").write_text("program_id,capacity\nP01,x\n", encoding="utf-8")
    out = tmp_path / "results"
    done = _run("match", "--input", str(data), "--out", str(out))
    assert done.returncode == 2
    assert "programs.csv row 1" in done.stderr
    assert not out.exists()


def test_exit_2_missing_directory(tmp_path: Path) -> None:
    """A missing input directory is an input error."""
    done = _run(
        "match", "--input", str(tmp_path / "nope"), "--out", str(tmp_path / "o")
    )
    assert done.returncode == 2
    assert "file not found" in done.stderr


def test_exit_3_bad_flag_and_missing_command() -> None:
    """Unknown flags and a missing command are usage errors."""
    assert _run("match", "--bogus").returncode == 3
    assert _run().returncode == 3
    assert _run("generate", "--seed", "abc", "--out", "x").returncode == 3


def test_non_terminal_missing_flags_listed_instead_of_prompting(tmp_path: Path) -> None:
    """Without a terminal, missing flags are an error naming each one."""
    done = _run("generate")
    assert done.returncode == 3
    assert "--seed" in done.stderr and "--out" in done.stderr
    done = _run("match", "--input", str(tmp_path))
    assert done.returncode == 3 and "--out" in done.stderr


def test_invalid_generator_parameters_are_usage_errors(tmp_path: Path) -> None:
    """Negative counts give status 3."""
    done = _run(
        "generate", "--seed", "1", "--applicants", "-5", "--out", str(tmp_path / "d")
    )
    assert done.returncode == 3


def test_generate_refuses_non_empty_directory_without_force(tmp_path: Path) -> None:
    """A non-empty output directory needs --force when not interactive."""
    data = _generate(tmp_path)
    again = _run("generate", "--seed", "1", "--out", str(data))
    assert again.returncode == 3 and "--force" in again.stderr
    assert (
        _run("generate", "--seed", "1", "--out", str(data), "--force").returncode == 0
    )


def test_quiet_prints_only_footer(tmp_path: Path) -> None:
    """--quiet leaves just the Wrote lines and the exit status."""
    data = tmp_path / "d"
    done = _run("generate", "--seed", "1", "--out", str(data), "--quiet")
    assert done.returncode == 0
    lines = [ln for ln in done.stdout.splitlines() if ln.strip()]
    assert all(ln.startswith(("Wrote", "Exit status")) for ln in lines)


def test_no_color_has_no_escape_codes(tmp_path: Path) -> None:
    """--no-color output contains no ANSI escapes."""
    data = _generate(tmp_path)
    done = _run(
        "match", "--input", str(data), "--out", str(tmp_path / "r"), "--no-color"
    )
    assert "\x1b[" not in done.stdout


def test_help_exits_zero() -> None:
    """--help prints usage and exits 0."""
    done = _run("--help")
    assert done.returncode == 0 and "generate" in done.stdout


def test_exit_1_when_a_validation_check_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A broken matcher fails validation: status 1, but outputs are still written."""
    data = _generate(tmp_path)

    class Broken:
        """Stand-in matcher that returns an unstable (empty) matching."""

        def __init__(self, market: object) -> None:
            """Ignore the market."""

        def run(self, on_round: object = None) -> Matching:
            """Return a matching with nobody matched."""
            return Matching([])

    monkeypatch.setattr(cli, "DeferredAcceptance", Broken)
    out = tmp_path / "results"
    console = Console(record=True, force_terminal=False)
    status = cli.main(
        ["match", "--input", str(data), "--out", str(out)],
        console=console,
        interactive=False,
    )
    assert status == 1
    assert "FAIL" in (out / "validation.csv").read_text(encoding="utf-8")
    assert "Exit status: 1" in console.export_text()


def test_prompts_fill_missing_values_on_a_terminal(tmp_path: Path) -> None:
    """Interactive mode asks for the seed and directory and accepts defaults."""
    asked: list[str] = []

    def prompt(question: str, default: str | None) -> str:
        """Answer seed and directory; accept defaults for the rest."""
        asked.append(question)
        if question == "Seed":
            return "5"
        if question == "Output directory":
            return str(tmp_path / "d")
        assert default is not None
        return default

    console = Console(record=True, force_terminal=False)
    status = cli.main(["generate"], console=console, interactive=True, prompt=prompt)
    assert status == 0
    assert asked[:2] == ["Seed", "Output directory"]
    assert (tmp_path / "d" / "applicants.csv").is_file()


def test_interactive_overwrite_confirmation(tmp_path: Path) -> None:
    """Declining the overwrite question stops with a usage error."""
    data = _generate(tmp_path)
    console = Console(record=True, force_terminal=False)
    args = ["generate", "--seed", "1", "--out", str(data)]
    accept = lambda _q, default: default or ""  # noqa: E731
    no = cli.main(
        args,
        console=console,
        interactive=True,
        prompt=accept,
        confirm=lambda _q: False,
    )
    yes = cli.main(
        args,
        console=console,
        interactive=True,
        prompt=accept,
        confirm=lambda _q: True,
    )
    assert (no, yes) == (3, 0)
