"""CSV loading and writing for the residency match simulator.

This module is the only place that reads or writes the CSV and JSON files. It
contains no matching logic and no console output.
"""

from __future__ import annotations

import json
import platform
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from residency_match.checks import CheckResult
from residency_match.errors import InputError
from residency_match.market import Market
from residency_match.matching import Matching
from residency_match.models import Applicant, Program, ValidationIssue

APPLICANTS_FILE = "applicants.csv"
PROGRAMS_FILE = "programs.csv"
APPLICANT_RANKINGS_FILE = "applicant_rankings.csv"
PROGRAM_RANKINGS_FILE = "program_rankings.csv"
MATCHES_FILE = "matches.csv"
PROGRAM_SUMMARY_FILE = "program_summary.csv"
VALIDATION_FILE = "validation.csv"
METADATA_FILE = "run_metadata.json"

#: Required columns for each input file, in canonical order.
INPUT_COLUMNS: dict[str, tuple[str, ...]] = {
    APPLICANTS_FILE: ("applicant_id", "lottery"),
    PROGRAMS_FILE: ("program_id", "capacity"),
    APPLICANT_RANKINGS_FILE: ("applicant_id", "rank", "program_id"),
    PROGRAM_RANKINGS_FILE: ("program_id", "rank", "applicant_id"),
}


def _parse_int(text: str) -> int | None:
    """Parse a base-10 integer, returning ``None`` if the text is not one."""
    try:
        return int(text.strip())
    except ValueError:
        return None


class CsvMarketLoader:
    """Reads and validates the four input files.

    All problems found across all files are collected, so the user can fix them
    in one pass. Row numbers are one-based and exclude the header row.

    Examples
    --------
    >>> market = CsvMarketLoader().load(Path("data"))  # doctest: +SKIP
    """

    def load(self, directory: Path) -> Market:
        """Load and validate a market.

        Parameters
        ----------
        directory : Path
            Directory holding the four input CSV files.

        Returns
        -------
        Market
            The validated problem.

        Raises
        ------
        InputError
            If any file is missing or fails any validation rule.
        """
        issues: list[ValidationIssue] = []
        frames = {
            name: self._read(directory / name, name, cols, issues)
            for name, cols in INPUT_COLUMNS.items()
        }
        applicants = self._applicants(frames[APPLICANTS_FILE], issues)
        programs = self._programs(frames[PROGRAMS_FILE], issues)
        # Reference sets come from the raw columns, so one bad row does not
        # cause follow-on "unknown id" errors; None means the file was unusable.
        a_frame, p_frame = frames[APPLICANTS_FILE], frames[PROGRAMS_FILE]
        a_ids = None if a_frame is None else set(a_frame["applicant_id"])
        p_ids = None if p_frame is None else set(p_frame["program_id"])
        a_lists = self._rankings(
            frames[APPLICANT_RANKINGS_FILE],
            APPLICANT_RANKINGS_FILE,
            ("applicant_id", "program_id"),
            a_ids,
            p_ids,
            issues,
        )
        p_lists = self._rankings(
            frames[PROGRAM_RANKINGS_FILE],
            PROGRAM_RANKINGS_FILE,
            ("program_id", "applicant_id"),
            p_ids,
            a_ids,
            issues,
        )
        if issues:
            raise InputError(issues)
        return Market(applicants, programs, a_lists, p_lists)

    def _read(
        self,
        path: Path,
        name: str,
        columns: tuple[str, ...],
        issues: list[ValidationIssue],
    ) -> pd.DataFrame | None:
        """Read one file as text; return ``None`` if missing or malformed."""
        if not path.is_file():
            issues.append(ValidationIssue(name, "file not found"))
            return None
        try:
            # dtype=str and no NA parsing: blank cells stay "" so we can report
            # them ourselves instead of having pandas turn them into NaN.
            frame = pd.read_csv(path, dtype=str, keep_default_na=False)
        except (
            pd.errors.ParserError,
            pd.errors.EmptyDataError,
            UnicodeDecodeError,
        ) as exc:
            issues.append(ValidationIssue(name, f"cannot parse file: {exc}"))
            return None
        found = list(frame.columns)
        missing = [c for c in columns if c not in found]
        extra = [c for c in found if c not in columns]
        if missing:
            issues.append(
                ValidationIssue(name, f"missing column(s): {', '.join(missing)}")
            )
        if extra:
            issues.append(
                ValidationIssue(name, f"unexpected column(s): {', '.join(extra)}")
            )
        if missing or extra:
            return None
        return frame

    def _applicants(
        self, frame: pd.DataFrame | None, issues: list[ValidationIssue]
    ) -> list[Applicant]:
        """Validate applicants.csv rows and build the applicants."""
        name = APPLICANTS_FILE
        out: list[Applicant] = []
        if frame is None:
            return out
        seen_ids: set[str] = set()
        seen_lottery: set[int] = set()
        for row, (aid, lot_text) in enumerate(
            zip(frame["applicant_id"], frame["lottery"], strict=True), 1
        ):
            ok = True
            if not aid:
                issues.append(ValidationIssue(name, "applicant_id is empty", row))
                ok = False
            elif aid in seen_ids:
                issues.append(
                    ValidationIssue(name, f"duplicate applicant_id {aid!r}", row)
                )
                ok = False
            seen_ids.add(aid)
            lottery = _parse_int(lot_text)
            if lottery is None:
                issues.append(
                    ValidationIssue(
                        name, f"lottery {lot_text!r} is not an integer", row
                    )
                )
                ok = False
            elif lottery in seen_lottery:
                issues.append(
                    ValidationIssue(name, f"duplicate lottery {lottery}", row)
                )
                ok = False
            elif ok:
                seen_lottery.add(lottery)
            if ok and lottery is not None:
                out.append(Applicant(aid, lottery))
        return out

    def _programs(
        self, frame: pd.DataFrame | None, issues: list[ValidationIssue]
    ) -> list[Program]:
        """Validate programs.csv rows and build the programs."""
        name = PROGRAMS_FILE
        out: list[Program] = []
        if frame is None:
            return out
        seen: set[str] = set()
        for row, (pid, cap_text) in enumerate(
            zip(frame["program_id"], frame["capacity"], strict=True), 1
        ):
            ok = True
            if not pid:
                issues.append(ValidationIssue(name, "program_id is empty", row))
                ok = False
            elif pid in seen:
                issues.append(
                    ValidationIssue(name, f"duplicate program_id {pid!r}", row)
                )
                ok = False
            seen.add(pid)
            capacity = _parse_int(cap_text)
            if capacity is None or capacity < 0:
                issues.append(
                    ValidationIssue(
                        name,
                        f"capacity {cap_text!r} is not a non-negative integer",
                        row,
                    )
                )
                ok = False
            if ok and capacity is not None:
                out.append(Program(pid, capacity))
        return out

    def _rankings(
        self,
        frame: pd.DataFrame | None,
        name: str,
        columns: tuple[str, str],
        owner_ids: set[str] | None,
        listed_ids: set[str] | None,
        issues: list[ValidationIssue],
    ) -> dict[str, list[str]]:
        """Validate a rankings file and return each owner's list in rank order.

        Parameters
        ----------
        frame : DataFrame or None
            The file contents, or ``None`` if it could not be read.
        name : str
            File name used in issues.
        columns : tuple of str
            ``(owner column, listed column)``, e.g. applicant then program.
        owner_ids, listed_ids : set of str or None
            Ids that must exist for the owner and listed columns; ``None``
            skips the check because the referenced file was unusable.
        issues : list of ValidationIssue
            Receives every problem found.
        """
        lists: dict[str, list[tuple[int, str]]] = {}
        first_row: dict[str, int] = {}
        if frame is None:
            return {}
        owner_col, listed_col = columns
        for row, (owner, rank_text, listed) in enumerate(
            zip(frame[owner_col], frame["rank"], frame[listed_col], strict=True), 1
        ):
            rank = _parse_int(rank_text)
            if not owner or not listed:
                issues.append(ValidationIssue(name, "empty id", row))
                continue
            if rank is None:
                issues.append(
                    ValidationIssue(name, f"rank {rank_text!r} is not an integer", row)
                )
                continue
            # Cross-file reference checks.
            if owner_ids is not None and owner not in owner_ids:
                issues.append(
                    ValidationIssue(name, f"unknown {owner_col} {owner!r}", row)
                )
                continue
            if listed_ids is not None and listed not in listed_ids:
                issues.append(
                    ValidationIssue(name, f"unknown {listed_col} {listed!r}", row)
                )
                continue
            lists.setdefault(owner, []).append((rank, listed))
            first_row.setdefault(owner, row)
        result: dict[str, list[str]] = {}
        for owner, entries in lists.items():
            ranks = sorted(r for r, _ in entries)
            if ranks != list(range(1, len(entries) + 1)):
                issues.append(
                    ValidationIssue(
                        name,
                        f"ranks for {owner!r} must be 1..{len(entries)} with no gaps "
                        f"or duplicates, got {ranks}",
                        first_row[owner],
                    )
                )
                continue
            ordered = [item for _, item in sorted(entries)]
            if len(set(ordered)) != len(ordered):
                issues.append(
                    ValidationIssue(
                        name, f"{owner!r} lists the same id twice", first_row[owner]
                    )
                )
                continue
            result[owner] = ordered
        return result


def _write_csv(path: Path, columns: Sequence[str], rows: list[list[str]]) -> None:
    """Write text rows as UTF-8 CSV with LF endings, a header and no index.

    Every cell is already a string, so blank fields are written as empty text
    and pandas never has to guess at types.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(rows, columns=list(columns), dtype=str)
    frame.to_csv(path, index=False, encoding="utf-8", lineterminator="\n")


def environment_versions() -> dict[str, str]:
    """Return the Python, NumPy and pandas versions for run metadata.

    Returns
    -------
    dict of str to str
        Keys ``python``, ``numpy`` and ``pandas``.
    """
    return {
        "python": platform.python_version(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
    }


def write_metadata(directory: Path, payload: dict[str, Any]) -> Path:
    """Write ``run_metadata.json`` (sorted keys, 2-space indent, LF, UTF-8).

    Parameters
    ----------
    directory : Path
        Target directory; created if needed.
    payload : dict
        JSON-serializable metadata.

    Returns
    -------
    Path
        The file written.
    """
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / METADATA_FILE
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def read_seed(directory: Path) -> int | None:
    """Read the seed from ``run_metadata.json`` in a data directory, if any.

    Parameters
    ----------
    directory : Path
        Directory that may hold ``run_metadata.json``.

    Returns
    -------
    int or None
        The recorded seed, or ``None`` if the file or key is absent or invalid.
    """
    path = directory / METADATA_FILE
    if not path.is_file():
        return None
    try:
        seed = json.loads(path.read_text(encoding="utf-8")).get("seed")
    except (json.JSONDecodeError, AttributeError, UnicodeDecodeError):
        return None
    return seed if isinstance(seed, int) and not isinstance(seed, bool) else None


class CsvMarketWriter:
    """Writes a Market as the four input CSV files (used by the generator)."""

    def write(self, market: Market, directory: Path) -> None:
        """Write the four input files in the documented long format.

        Parameters
        ----------
        market : Market
            The market to write.
        directory : Path
            Target directory; created if needed.
        """
        _write_csv(
            directory / APPLICANTS_FILE,
            INPUT_COLUMNS[APPLICANTS_FILE],
            [[a.applicant_id, str(a.lottery)] for a in market.applicants],
        )
        _write_csv(
            directory / PROGRAMS_FILE,
            INPUT_COLUMNS[PROGRAMS_FILE],
            [[p.program_id, str(p.capacity)] for p in market.programs],
        )
        _write_csv(
            directory / APPLICANT_RANKINGS_FILE,
            INPUT_COLUMNS[APPLICANT_RANKINGS_FILE],
            [
                [a.applicant_id, str(i), p]
                for a in market.applicants
                for i, p in enumerate(market.applicant_lists[a.applicant_id], 1)
            ],
        )
        _write_csv(
            directory / PROGRAM_RANKINGS_FILE,
            INPUT_COLUMNS[PROGRAM_RANKINGS_FILE],
            [
                [p.program_id, str(i), a]
                for p in market.programs
                for i, a in enumerate(market.program_lists[p.program_id], 1)
            ],
        )


class CsvResultWriter:
    """Writes the match outputs: matches, program summary, validation, metadata.

    All files are UTF-8 with LF line endings, a header row and no index column.
    Empty fields are blank.

    Parameters
    ----------
    directory : Path
        Output directory; created on first write.
    """

    def __init__(self, directory: Path) -> None:
        """Remember the output directory."""
        self.directory = directory

    def write_matches(self, market: Market, matching: Matching) -> Path:
        """Write ``matches.csv``, one row per applicant sorted by applicant_id.

        Unmatched applicants get blank program_id, applicant_rank and
        program_rank.

        Returns
        -------
        Path
            The file written.
        """
        by_applicant = {m.applicant_id: m for m in matching.to_matches(market)}
        rows: list[list[str]] = []
        for aid in sorted(a.applicant_id for a in market.applicants):
            m = by_applicant.get(aid)
            if m is None:
                rows.append([aid, "", "", ""])
            else:
                rows.append(
                    [aid, m.program_id, str(m.applicant_rank), str(m.program_rank)]
                )
        path = self.directory / MATCHES_FILE
        _write_csv(
            path, ["applicant_id", "program_id", "applicant_rank", "program_rank"], rows
        )
        return path

    def write_program_summary(self, market: Market, matching: Matching) -> Path:
        """Write ``program_summary.csv``, one row per program sorted by id.

        Returns
        -------
        Path
            The file written.
        """
        rows: list[list[str]] = []
        for p in sorted(market.programs, key=lambda p: p.program_id):
            filled = len(matching.holders(p.program_id))
            rows.append(
                [p.program_id, str(p.capacity), str(filled), str(p.capacity - filled)]
            )
        path = self.directory / PROGRAM_SUMMARY_FILE
        _write_csv(path, ["program_id", "capacity", "filled", "unfilled"], rows)
        return path

    def write_validation(self, results: Sequence[CheckResult]) -> Path:
        """Write ``validation.csv``.

        Each check gets one PASS or FAIL row. Each problem a check found gets
        an extra FAIL row after it, with the problem in ``detail`` (for
        Stability, the applicant and program of the blocking pair).

        Returns
        -------
        Path
            The file written.
        """
        rows: list[list[str]] = []
        for r in results:
            rows.append([r.check, "PASS" if r.passed else "FAIL", ""])
            rows.extend([r.check, "FAIL", i.detail] for i in r.issues)
        path = self.directory / VALIDATION_FILE
        _write_csv(path, ["check", "result", "detail"], rows)
        return path

    def write_match_metadata(
        self, input_dir: Path, now: datetime, seed: int | None
    ) -> Path:
        """Write ``run_metadata.json`` for a match run.

        Parameters
        ----------
        input_dir : Path
            The data directory that was matched.
        now : datetime
            Timestamp to record (injected so tests are deterministic).
        seed : int or None
            Seed copied from the input metadata, or ``None`` if unavailable.

        Returns
        -------
        Path
            The file written.
        """
        return write_metadata(
            self.directory,
            {
                "input_directory": str(input_dir),
                "timestamp": now.isoformat(timespec="seconds"),
                "versions": environment_versions(),
                "seed": seed,
            },
        )
