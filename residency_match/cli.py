"""Command-line interface: argument parsing, prompting and dispatch.

This module wires the other modules together for the ``generate`` and ``match``
commands and maps outcomes to exit codes. It holds no matching or file-format
logic of its own. Everything that touches the outside world (console, prompts,
clock, interactivity) is injected into :func:`main` so tests can drive it.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from typing import NoReturn

from rich.console import Console
from rich.prompt import Confirm, Prompt

from residency_match.checks import Validator
from residency_match.console import ConsoleReporter
from residency_match.errors import InputError, ResidencyMatchError, UsageError
from residency_match.generate import generate_files
from residency_match.io import CsvMarketLoader, CsvResultWriter, read_seed
from residency_match.matching import DeferredAcceptance
from residency_match.models import GeneratorConfig

#: ``prompt(question, default)`` returns the typed answer (default if empty).
Prompter = Callable[[str, str | None], str]
#: ``confirm(question)`` returns True for yes.
Confirmer = Callable[[str], bool]

EXIT_OK = 0
EXIT_VALIDATION_FAILED = 1


class _Parser(argparse.ArgumentParser):
    """ArgumentParser that raises UsageError instead of exiting with status 2."""

    def error(self, message: str) -> NoReturn:
        """Raise a UsageError (exit status 3) for any parsing problem."""
        raise UsageError(f"{self.prog}: {message}")


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser with the generate and match commands.

    Returns
    -------
    argparse.ArgumentParser
        Parser whose errors raise :class:`UsageError`.
    """
    parser = _Parser(prog="residency_match", description="Residency match simulator.")
    sub = parser.add_subparsers(dest="command", required=True, parser_class=_Parser)

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--quiet", action="store_true", help="print only the footer")
        p.add_argument("--no-color", action="store_true", help="turn off color")

    gen = sub.add_parser("generate", help="generate seeded mock data")
    gen.add_argument("--seed", type=int, help="random seed (required)")
    gen.add_argument("--applicants", type=int, help="number of applicants (20)")
    gen.add_argument("--programs", type=int, help="number of programs (5)")
    gen.add_argument("--capacity-min", type=int, help="minimum capacity (2)")
    gen.add_argument("--capacity-max", type=int, help="maximum capacity (6)")
    gen.add_argument("--applicant-list-length", type=int, help="programs ranked (5)")
    gen.add_argument("--program-list-length", type=int, help="applicants ranked (all)")
    gen.add_argument("--out", type=Path, help="output directory (required)")
    gen.add_argument(
        "--force", action="store_true", help="overwrite a non-empty directory"
    )
    common(gen)

    match = sub.add_parser("match", help="run the match and validate it")
    match.add_argument("--input", type=Path, help="data directory (required)")
    match.add_argument("--out", type=Path, help="results directory (required)")
    common(match)
    return parser


def _default_prompt(question: str, default: str | None) -> str:
    """Ask on the terminal with Rich, showing the default if there is one."""
    return (
        Prompt.ask(question, default=default)
        if default is not None
        else (Prompt.ask(question))
    )


def _default_confirm(question: str) -> bool:
    """Ask a yes/no question on the terminal with Rich."""
    return Confirm.ask(question, default=False)


class _Asker:
    """Fills in values left out of the flags, prompting only on a terminal.

    Parameters
    ----------
    interactive : bool
        Whether prompts are allowed.
    prompt : Prompter
        Asks for one value.
    """

    def __init__(self, interactive: bool, prompt: Prompter) -> None:
        """Store the settings and start with no missing required flags."""
        self._interactive = interactive
        self._prompt = prompt
        self.missing: list[str] = []

    def required(self, value: str | None, flag: str, question: str) -> str | None:
        """Return the flag value, a prompted answer, or record it as missing."""
        if value is not None:
            return value
        if not self._interactive:
            self.missing.append(flag)
            return None
        return self._prompt(question, None)

    def optional(
        self, value: int | None, question: str, default: int | None
    ) -> int | None:
        """Return the flag value, a prompted answer (Enter keeps the default)."""
        if value is not None or not self._interactive:
            return value if value is not None else default
        answer = self._prompt(question, "all" if default is None else str(default))
        if answer == "all":
            return None
        try:
            return int(answer)
        except ValueError:
            raise UsageError(f"{question}: {answer!r} is not an integer") from None


def _run_generate(
    args: argparse.Namespace,
    reporter: ConsoleReporter,
    asker: _Asker,
    confirm: Confirmer,
    interactive: bool,
    now: datetime,
) -> int:
    """Run the generate command and return its exit status."""
    seed_text = asker.required(
        None if args.seed is None else str(args.seed), "--seed", "Seed"
    )
    out_text = asker.required(
        None if args.out is None else str(args.out), "--out", "Output directory"
    )
    if asker.missing:
        raise UsageError(f"missing required flag(s): {', '.join(asker.missing)}")
    assert seed_text is not None and out_text is not None
    try:
        seed = int(seed_text)
    except ValueError:
        raise UsageError(f"seed {seed_text!r} is not an integer") from None
    out = Path(out_text)

    config = GeneratorConfig(
        seed=seed,
        applicants=asker.optional(args.applicants, "Applicants", 20) or 0,
        programs=asker.optional(args.programs, "Programs", 5) or 0,
        capacity_min=asker.optional(args.capacity_min, "Capacity min", 2) or 0,
        capacity_max=asker.optional(args.capacity_max, "Capacity max", 6) or 0,
        applicant_list_length=asker.optional(
            args.applicant_list_length, "Applicant list length", 5
        )
        or 0,
        program_list_length=asker.optional(
            args.program_list_length, "Program list length", None
        ),
    )

    if out.is_dir() and any(out.iterdir()) and not args.force:
        if not interactive:
            raise UsageError(f"{out} is not empty; pass --force to overwrite")
        if not confirm(f"{out} is not empty. Overwrite?"):
            raise UsageError("not overwriting a non-empty directory")

    market = generate_files(config, out, now)
    reporter.header(config.seed, market, now)
    reporter.inputs_summary(market)
    paths = sorted(p for p in out.iterdir() if p.is_file())
    reporter.footer(paths, EXIT_OK)
    return EXIT_OK


def _run_match(
    args: argparse.Namespace,
    reporter: ConsoleReporter,
    asker: _Asker,
    now: datetime,
) -> int:
    """Run the match command and return its exit status."""
    input_text = asker.required(
        None if args.input is None else str(args.input), "--input", "Input directory"
    )
    out_text = asker.required(
        None if args.out is None else str(args.out), "--out", "Results directory"
    )
    if asker.missing:
        raise UsageError(f"missing required flag(s): {', '.join(asker.missing)}")
    assert input_text is not None and out_text is not None
    input_dir, out_dir = Path(input_text), Path(out_text)

    market = CsvMarketLoader().load(input_dir)  # raises InputError before any output
    seed = read_seed(input_dir)
    reporter.header(seed, market, now)
    reporter.inputs_summary(market)
    with reporter.progress() as on_round:
        matching = DeferredAcceptance(market).run(on_round)
    results = Validator.default().run(market, matching)
    reporter.matches_table(market, matching)
    reporter.programs_table(market, matching)
    reporter.validation_panel(results)

    writer = CsvResultWriter(out_dir)
    paths = [
        writer.write_matches(market, matching),
        writer.write_program_summary(market, matching),
        writer.write_validation(results),
        writer.write_match_metadata(input_dir, now, seed),
    ]
    status = EXIT_OK if all(r.passed for r in results) else EXIT_VALIDATION_FAILED
    reporter.footer(paths, status)
    return status


def main(
    argv: Sequence[str] | None = None,
    *,
    console: Console | None = None,
    interactive: bool | None = None,
    prompt: Prompter = _default_prompt,
    confirm: Confirmer = _default_confirm,
    clock: Callable[[], datetime] = datetime.now,
) -> int:
    """Run the program.

    Parameters
    ----------
    argv : Sequence[str], optional
        Arguments after the program name; defaults to ``sys.argv[1:]``.
    console : rich.console.Console, optional
        Output console; built from ``--no-color`` if omitted.
    interactive : bool, optional
        Whether prompts are allowed; defaults to whether stdin and stdout are
        terminals.
    prompt, confirm : callable
        Injected prompt functions.
    clock : callable
        Returns the current time.

    Returns
    -------
    int
        Exit status: 0 success, 1 a validation check failed, 2 input error,
        3 usage error.
    """
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as exc:  # --help
        return int(exc.code) if isinstance(exc.code, int) else 0
    except UsageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.exit_code

    if console is None:
        console = Console(no_color=args.no_color)
    if interactive is None:
        interactive = sys.stdin.isatty() and console.is_terminal
    reporter = ConsoleReporter(console, quiet=args.quiet)
    asker = _Asker(interactive, prompt)
    now = clock()
    try:
        if args.command == "generate":
            return _run_generate(args, reporter, asker, confirm, interactive, now)
        return _run_match(args, reporter, asker, now)
    except InputError as exc:
        reporter.input_errors(exc.issues)
        reporter.footer([], exc.exit_code)
        return exc.exit_code
    except ResidencyMatchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.exit_code
