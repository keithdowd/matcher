"""CSV loading and writing for the residency match simulator.

This module is the only place that reads or writes the CSV and JSON files. It
contains no matching logic and no console output.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from residency_match.errors import InputError
from residency_match.market import Market
from residency_match.models import Applicant, Program, ValidationIssue

APPLICANTS_FILE = "applicants.csv"
PROGRAMS_FILE = "programs.csv"
APPLICANT_RANKINGS_FILE = "applicant_rankings.csv"
PROGRAM_RANKINGS_FILE = "program_rankings.csv"

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
