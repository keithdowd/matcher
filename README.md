# Residency Match Simulator

A Python console program that generates seeded mock data for applicants and
programs, runs resident-proposing deferred acceptance on it, and writes the
matches and a validation report as CSV.

Version 1 simulates one match cycle for a single track. The same seed always
produces the same inputs and outputs.

## Features

- Seeded mock data: applicants, programs, capacities and strict rankings.
- Resident-proposing deferred acceptance, giving the applicant-optimal stable
  matching.
- Five validation checks after every match: capacity, single match, listed
  pairs only, stability and reproducibility.
- CSV outputs plus run metadata, and a Rich console display.
- Input validation that reports every problem with its file name and row.

## Requirements

Python 3.13.6. Dependencies are pinned in `pyproject.toml` and
`requirements.txt`: NumPy, pandas and Rich at run time; pytest, Hypothesis,
Ruff, mypy and pandas-stubs for development.

## Install

```text
python -m venv .venv
.venv\Scripts\activate          # Windows; use source .venv/bin/activate elsewhere
pip install -r requirements.txt
pip install -e .
```

## Quick start

```text
python -m residency_match generate --seed 42 --applicants 20 --programs 5 --out data/
python -m residency_match match --input data/ --out results/
```

`generate` writes four input CSV files and `run_metadata.json` to `data/`.
`match` reads them and writes `matches.csv`, `program_summary.csv`,
`validation.csv` and `run_metadata.json` to `results/`.

See [USER_GUIDE.md](USER_GUIDE.md) for every flag, the file formats, exit codes
and a list of features worth testing.

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Success, and all validation checks pass |
| 1 | A validation check failed (outputs are still written) |
| 2 | Input error (nothing is written) |
| 3 | Usage error, such as a bad flag |

## Development

```text
ruff check .
ruff format --check .
mypy residency_match tests
pytest
```

`pytest` also runs the docstring examples. The design is in
[Residency Match Simulator Version 1 Design.md](<Residency Match Simulator Version 1 Design.md>),
including the build log.

## Layout

```text
residency_match/
  cli.py        argument parsing and dispatch
  console.py    Rich-based console output
  checks.py     validation checks and the validator
  errors.py     exception hierarchy
  generate.py   seeded mock data generator
  io.py         CSV loading and writing
  market.py     immutable problem definition
  matching.py   deferred acceptance and matching results, no I/O
  models.py     frozen dataclasses
tests/          unit, property, golden-file and subprocess tests
```

## Out of scope for version 1

Score-based rankings with ties, a generative ranking model, Monte Carlo runs,
sensitivity analysis, quotas, couples, a second round and plots. See the design
document for the full list.
