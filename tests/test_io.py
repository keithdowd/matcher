"""Tests for CsvMarketLoader: one fixture per validation rule."""

from pathlib import Path

import pytest

from residency_match.errors import InputError
from residency_match.io import CsvMarketLoader

GOOD = {
    "applicants.csv": "applicant_id,lottery\nA1,2\nA2,1\n",
    "programs.csv": "program_id,capacity\nP1,1\nP2,0\n",
    "applicant_rankings.csv": (
        "applicant_id,rank,program_id\nA1,1,P1\nA1,2,P2\nA2,1,P1\n"
    ),
    "program_rankings.csv": "program_id,rank,applicant_id\nP1,1,A2\nP1,2,A1\n",
}


def _write(tmp: Path, **overrides: str | None) -> Path:
    """Write the good fixture, replacing or (if None) omitting named files."""
    for name, text in GOOD.items():
        key = name.removesuffix(".csv")
        if key in overrides:
            text = overrides[key]  # type: ignore[assignment]
        if text is not None:
            (tmp / name).write_text(text, encoding="utf-8", newline="\n")
    return tmp


def _issues(tmp: Path) -> list[str]:
    """Load and return the formatted issues of the InputError."""
    with pytest.raises(InputError) as info:
        CsvMarketLoader().load(tmp)
    return [str(i) for i in info.value.issues]


def test_valid_files_load(tmp_path: Path) -> None:
    """A valid directory yields a Market with lists in rank order."""
    market = CsvMarketLoader().load(_write(tmp_path))
    assert market.applicant_lists["A1"] == ("P1", "P2")
    assert market.program_lists["P1"] == ("A2", "A1")
    assert market.capacity("P2") == 0
    assert market.lottery("A2") == 1


def test_rows_may_be_in_any_order(tmp_path: Path) -> None:
    """Rank, not row order, decides list order."""
    rankings = "applicant_id,rank,program_id\nA1,2,P2\nA1,1,P1\n"
    market = CsvMarketLoader().load(_write(tmp_path, applicant_rankings=rankings))
    assert market.applicant_lists["A1"] == ("P1", "P2")


def test_missing_file(tmp_path: Path) -> None:
    """A missing file is reported by name."""
    issues = _issues(_write(tmp_path, programs=None))
    assert "programs.csv: file not found" in issues


def test_missing_and_extra_columns(tmp_path: Path) -> None:
    """Missing and extra columns are both errors."""
    issues = _issues(
        _write(
            tmp_path,
            applicants="applicant_id\nA1\n",
            programs="program_id,capacity,notes\nP1,1,x\n",
        )
    )
    assert "applicants.csv: missing column(s): lottery" in issues
    assert "programs.csv: unexpected column(s): notes" in issues


def test_empty_and_duplicate_ids(tmp_path: Path) -> None:
    """Empty and duplicate ids carry the row number."""
    issues = _issues(
        _write(
            tmp_path,
            applicants="applicant_id,lottery\n,1\nA1,2\nA1,3\n",
            programs="program_id,capacity\nP1,1\nP1,2\n",
        )
    )
    assert "applicants.csv row 1: applicant_id is empty" in issues
    assert "applicants.csv row 3: duplicate applicant_id 'A1'" in issues
    assert "programs.csv row 2: duplicate program_id 'P1'" in issues


def test_bad_and_duplicate_lottery(tmp_path: Path) -> None:
    """Lottery must be an integer and unique."""
    issues = _issues(
        _write(tmp_path, applicants="applicant_id,lottery\nA1,x\nA2,5\nA3,5\n")
    )
    assert "applicants.csv row 1: lottery 'x' is not an integer" in issues
    assert "applicants.csv row 3: duplicate lottery 5" in issues


def test_bad_capacity(tmp_path: Path) -> None:
    """Capacity must be a non-negative integer."""
    issues = _issues(_write(tmp_path, programs="program_id,capacity\nP1,-1\nP2,1.5\n"))
    assert "programs.csv row 1: capacity '-1' is not a non-negative integer" in issues
    assert "programs.csv row 2: capacity '1.5' is not a non-negative integer" in issues


def test_rank_gaps_and_duplicates(tmp_path: Path) -> None:
    """Ranks must run 1..n with no gaps or duplicates."""
    gap = "applicant_id,rank,program_id\nA1,1,P1\nA1,3,P2\n"
    dup = "program_id,rank,applicant_id\nP1,1,A1\nP1,1,A2\n"
    issues = _issues(_write(tmp_path, applicant_rankings=gap, program_rankings=dup))
    assert any("applicant_rankings.csv row 1: ranks for 'A1'" in i for i in issues)
    assert any("program_rankings.csv row 1: ranks for 'P1'" in i for i in issues)


def test_rank_not_starting_at_one_or_not_integer(tmp_path: Path) -> None:
    """Ranks starting at 0 or non-numeric ranks are errors."""
    zero = "applicant_id,rank,program_id\nA1,0,P1\nA1,1,P2\n"
    text = "program_id,rank,applicant_id\nP1,first,A1\n"
    issues = _issues(_write(tmp_path, applicant_rankings=zero, program_rankings=text))
    assert any("ranks for 'A1'" in i for i in issues)
    assert "program_rankings.csv row 1: rank 'first' is not an integer" in issues


def test_unknown_references(tmp_path: Path) -> None:
    """Rankings must reference ids that exist in the other files."""
    a = "applicant_id,rank,program_id\nA1,1,PX\nAX,1,P1\n"
    p = "program_id,rank,applicant_id\nP1,1,AY\n"
    issues = _issues(_write(tmp_path, applicant_rankings=a, program_rankings=p))
    assert "applicant_rankings.csv row 1: unknown program_id 'PX'" in issues
    assert "applicant_rankings.csv row 2: unknown applicant_id 'AX'" in issues
    assert "program_rankings.csv row 1: unknown applicant_id 'AY'" in issues


def test_same_program_listed_twice(tmp_path: Path) -> None:
    """Listing one program twice for an applicant is an error."""
    a = "applicant_id,rank,program_id\nA1,1,P1\nA1,2,P1\n"
    issues = _issues(_write(tmp_path, applicant_rankings=a))
    assert any("lists the same id twice" in i for i in issues)


def test_all_issues_reported_together(tmp_path: Path) -> None:
    """Problems in several files are collected into one error."""
    issues = _issues(
        _write(tmp_path, applicants="applicant_id,lottery\nA1,x\n", programs=None)
    )
    assert len(issues) >= 2


def test_edge_inputs_are_valid(tmp_path: Path) -> None:
    """Zero capacity, empty lists and unranked programs all load."""
    market = CsvMarketLoader().load(
        _write(
            tmp_path,
            applicant_rankings="applicant_id,rank,program_id\n",
            program_rankings="program_id,rank,applicant_id\n",
        )
    )
    assert market.acceptable_pairs() == []
