# User Guide

This guide explains how to run the residency match simulator and lists features
worth testing. Run the commands from the project folder with the virtual
environment active (see the README for install steps).

## 1. The two commands

### generate

Creates seeded mock data.

```text
python -m residency_match generate --seed 42 --applicants 20 --programs 5 --out data/
```

| Flag | Default | Meaning |
| --- | --- | --- |
| `--seed` | required | Fixes every random draw |
| `--applicants` | 20 | Number of applicants |
| `--programs` | 5 | Number of programs |
| `--capacity-min`, `--capacity-max` | 2, 6 | Each program's seat count is drawn uniformly from this range |
| `--applicant-list-length` | 5 | Programs each applicant ranks |
| `--program-list-length` | all applicants | Applicants each program ranks |
| `--out` | required | Output directory |
| `--force` | off | Overwrite a non-empty output directory without asking |
| `--quiet` | off | Print only the footer |
| `--no-color` | off | Turn off color |

If a list length is larger than what exists (for example 9 programs ranked out
of 5), it is reduced to what exists. The values actually used are recorded in
`run_metadata.json` under `effective`.

### match

Runs deferred acceptance on a data directory, validates the result and writes
the outputs.

```text
python -m residency_match match --input data/ --out results/
```

| Flag | Meaning |
| --- | --- |
| `--input` | Directory with the four input files (required) |
| `--out` | Results directory (required) |
| `--quiet`, `--no-color` | As above |

### Prompts

In a terminal, any flag you leave out is asked for, and pressing Enter accepts
the default shown. When output is piped or there is no terminal, nothing is
prompted: missing required flags (`--seed`, `--out`, `--input`) produce an
error listing them, and the other values use their defaults.

## 2. Input files

All four are CSV files in long format, one row per record.

| File | Columns |
| --- | --- |
| `applicants.csv` | `applicant_id`, `lottery` |
| `programs.csv` | `program_id`, `capacity` |
| `applicant_rankings.csv` | `applicant_id`, `rank`, `program_id` |
| `program_rankings.csv` | `program_id`, `rank`, `applicant_id` |

Rank 1 is most preferred, and ranks must run 1, 2, 3 and so on with no gaps or
duplicates in each list. A pair can match only if **both** sides list each
other. You can write your own files by hand to test a specific case.

Rules checked before any matching (every failure is reported with its file and
row, and the program exits with status 2):

- Column names match exactly, with no extra columns.
- Ids are non-empty and unique; lottery numbers are unique integers.
- Capacity is a non-negative integer.
- Ranks are integers forming 1..n in each list.
- Rankings refer only to ids that exist.

Valid edge cases: zero-capacity programs, applicants with no list, programs that
rank nobody, and more seats than applicants.

## 3. Outputs

| File | Contents |
| --- | --- |
| `matches.csv` | One row per applicant: `applicant_id`, `program_id`, `applicant_rank`, `program_rank`. Unmatched applicants have blanks. |
| `program_summary.csv` | One row per program: `capacity`, `filled`, `unfilled`. |
| `validation.csv` | One PASS or FAIL row per check, plus a FAIL row for each problem found. |
| `run_metadata.json` | Input directory, timestamp, library versions, and the seed (null if the input had no metadata). |

Files are UTF-8 with LF line endings and no index column.

## 4. The console display

A match run shows, in order: a header (seed, counts, time), an inputs summary,
a spinner during the proposal rounds, the matches table (rank 1 green, lower
ranks yellow, unmatched red), the programs table with a fill bar, the validation
panel, and a footer with the files written and the exit status. When output is
piped, color and the spinner are dropped automatically.

## 5. Exit codes

| Code | Meaning | Outputs written |
| --- | --- | --- |
| 0 | Success, all checks pass | Yes |
| 1 | A validation check failed | Yes |
| 2 | Input error | No |
| 3 | Usage error | No |

## 6. Features worth testing

1. **Reproducibility.** Run `generate` twice with the same seed into two
   folders and compare the CSV files; they should be byte-identical. A different
   seed should give different data.
2. **Round trip.** Run `match` on each folder and compare `matches.csv`.
3. **Hand-built cases.** Write small input files and check the answer by hand.
   Try a program that prefers an applicant who ranks it second, so that
   someone is displaced mid-run.
4. **Mutual listing.** Make an applicant list a program that does not rank them.
   They must stay unmatched even if the program has empty seats.
5. **Edge inputs.** Zero capacity, empty lists, one applicant, no programs.
6. **Input errors.** Break a file on purpose (bad capacity, duplicate lottery,
   rank gap, unknown id, extra column, missing file) and confirm the message
   names the file and row, the exit status is 2 and no output folder appears.
7. **Usage errors.** Pass an unknown flag or a non-numeric seed; expect status 3.
8. **Overwrite protection.** Run `generate` into an existing non-empty folder.
   In a terminal you are asked; when piped it fails unless `--force` is given.
9. **Quiet and no-color.** `--quiet` prints only the footer; `--no-color`
   output has no escape codes.
10. **Scale.** Try `--applicants 500 --programs 30`. The stability check is
    quadratic in pairs but should stay fast.
11. **Clamping.** Ask for `--applicant-list-length 50` with 5 programs and check
    `effective` in `run_metadata.json`.
12. **Validation failure.** The real matcher always passes; to see the failing
    path, run the test `test_exit_1_when_a_validation_check_fails`.

## 7. Running the automated tests

```text
pytest
```

The suite includes brute-force comparison against every stable matching on
small markets, Hypothesis property tests, golden-file output tests, subprocess
exit-code tests and docstring examples.
