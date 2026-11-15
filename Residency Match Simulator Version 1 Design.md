# Residency Match Simulator: Version 1 Design

Nov 14, 2026 · @Keith Dowd

Version 1 is a Python console program that generates seeded mock data for applicants and programs, runs resident-proposing deferred acceptance on it, and writes the matches and a validation report as CSV.

## Scope

Version 1 simulates one match cycle for a single track. Mock data is generated from a seed, so the same seed always produces the same inputs and outputs.

Included in version 1:

- One integer capacity per program, with all applicants competing for those seats.
- Resident-proposing deferred acceptance.
- One global lottery number per applicant, used for every tie.
- Seeded mock data for applicants, program rankings, and capacities.
- CSV match output and a validation report.
- A console interface with separate generate and match commands.

The target scale is about 20 applicants and 5 programs. Excluded items are listed under future work.

## Inputs

The matcher reads four CSV files in long format, one row per pair or per record. This layout avoids quoted lists inside cells. The format is settled for version 1.

| File | Columns | Meaning |
| --- | --- | --- |
| applicants.csv | applicant\_id, lottery | One row per applicant. The lottery is a number drawn once per applicant and used for all ties. |
| programs.csv | program\_id, capacity | One row per program. Capacity is a non-negative integer. |
| applicant\_rankings.csv | applicant\_id, rank, program\_id | One row per listed program. Rank 1 is the most preferred, and ranks have no gaps or duplicates. |
| program\_rankings.csv | program\_id, rank, applicant\_id | One row per applicant the program ranks. Rank 1 is the most preferred, and ranks have no gaps or duplicates. |

Unlisted pairs are unacceptable on both sides. A program that does not rank an applicant cannot match with that applicant, and an applicant who does not list a program cannot match with it.

The four files are separate CSVs, one per record type.

## Mock data generator

The generator draws all randomness from one NumPy random generator created from a single seed. Each file it writes uses the input format in the Inputs section, and it also writes a metadata file that records the seed and parameters.

| Parameter | Default | Effect |
| --- | --- | --- |
| seed | required | Fixes every random draw |
| applicants | 20 | Number of applicants |
| programs | 5 | Number of programs |
| capacity\_min, capacity\_max | 2, 6 | Each program's capacity is drawn uniformly from this range |
| applicant\_list\_length | 5 | Number of programs each applicant ranks |
| program\_list\_length | all applicants | Number of applicants each program ranks |

Lottery numbers are a random permutation of the integers from 1 to the applicant count, so no two applicants tie on the lottery. Each applicant's program list is a random sample of programs in random order. Each program's ranking is a random permutation of its ranked applicants.

These uniform draws are a placeholder. The generative model for realistic rankings is a future feature.

## Algorithm

The matcher runs resident-proposing deferred acceptance. The result is the applicant-optimal stable matching, and it is strategy-proof for applicants.

1. Every applicant starts unmatched, with a pointer at the first program on their list.
2. Each unmatched applicant proposes to the program at their pointer.
3. Each program holds the applicants it ranks highest, up to its capacity, from among its current holds and this round's proposers.
4. Each applicant not held by a program moves the pointer to their next program. An applicant with no programs left stays unmatched.
5. Repeat steps 2 to 4 until no applicant has a proposal outstanding.
6. The final holds are the matching.

Each applicant-program pair is proposed at most once, so the run ends after at most the total length of all applicant lists. Version 1 program rankings are strict orders, so the lottery is never needed to break a tie in the mock data. The lottery is applied only if a future input carries tied scores. In that case, the applicant with the lower lottery number ranks higher. This convention is fixed for version 1.

## Outputs and validation

Each match run writes three CSV files to the output directory.

| File | Contents |
| --- | --- |
| matches.csv | One row per applicant with applicant\_id, program\_id, applicant\_rank, and program\_rank. Unmatched applicants have an empty program\_id. |
| program\_summary.csv | One row per program with capacity, filled seats, and unfilled seats. |
| validation.csv | One row per check with check, result, and detail. |

The validation checks run after every match:

| Check | Pass condition |
| --- | --- |
| Capacity | No program holds more applicants than its capacity |
| Single match | Each applicant appears in at most one match |
| Listed pairs only | Every match is a pair that both sides list |
| Stability | No blocking pair exists, meaning no applicant and program both prefer each other to their outcomes |
| Reproducibility | Re-running the matcher on the same loaded market reproduces the same matches |

Each blocking pair found is written to validation.csv as a detail row. The stability check is quadratic in the number of pairs, which is fast at the target scale.

## Command-line interface and project layout

The program has two commands. Each takes an input or output directory.

```text
python -m residency_match generate --seed 42 --applicants 20 --programs 5 --out data/
python -m residency_match match --input data/ --out results/
```

The match command runs the algorithm, then the validation checks, then writes the three output files. It exits with a nonzero status if any validation check fails.

The layout separates the algorithm from input and output, so the matcher can be tested without files.

```text
residency_match/
  __init__.py
  __main__.py     entry point
  cli.py          argument parsing and dispatch
  errors.py       exception hierarchy
  models.py       frozen dataclasses
  market.py       immutable problem definition
  matching.py     deferred acceptance and matching results, no I/O
  checks.py       validation checks and the validator
  io.py           CSV loading and writing
  generate.py     seeded mock data generator
  console.py      Rich-based console output
tests/
  test_matching.py
  test_checks.py
  test_generate.py
  test_io.py
```

## Console output

The console output is built with Rich, the one dependency outside the data science stack. It was approved for this purpose.

Run settings come from command-line flags. Any value left out is prompted for when the command runs in a terminal. The seed is printed at the top of every run and saved to the metadata file, so any run can be reproduced.

A match run shows these parts, in order:

- A header panel with the seed, applicant and program counts, and the time.
- An inputs summary with applicant and seat totals and average ranking lengths.
- A live progress spinner that updates each round of proposals.
- A matches table, with rank 1 matches in green, lower ranks in yellow, and unmatched applicants in red.
- A programs table with capacity, filled and unfilled seats, and a fill bar.
- A validation panel with one pass or fail line per check.
- A footer with the output paths and the exit status.

Interactivity is limited to the following:

- Generate asks before overwriting a non-empty output directory.
- The --quiet flag suppresses everything except the footer, for scripts.
- The --no-color flag turns off color, for logs and pipes.
- No menus or pagers.

When output is piped, Rich drops color and the spinner automatically. Any prompt that would have appeared becomes an error that lists the missing flags.

## Dependencies and test plan

The project targets Python 3.13.6 and uses the data science stack plus Rich for console output.

| Package | Role |
| --- | --- |
| NumPy | Seeded random generation for mock data |
| pandas | Reading and writing the CSV files, and building summary tables |
| pytest | Test runner |
| Hypothesis | Property-based tests on random instances |
| Rich | Console output, as approved for this purpose |
| Ruff | Linting and formatting, development only, as approved |
| mypy | Static type checking in strict mode, development only, as approved |

The test plan has four parts:

1. Known answers: small hand-checked instances with one correct matching each.
2. Brute force: on instances of up to four applicants and four programs, enumerate every stable matching and confirm the algorithm returns the one applicants prefer most.
3. Properties: for random instances, every output passes the feasibility and stability checks.
4. Reproducibility: the same seed produces identical input files and identical matches.

## Implementation specifications

These rules apply to version 1 only.

### Input validation

The match command checks all four files before it runs. The generate command runs the same check on its output before it writes the metadata file, so a generator bug fails at generation time. Both commands report every failure with the file name and row number, then exit with status 2.

- Required columns exist with the names in the Inputs table. Extra columns are an error.
- applicant\_id and program\_id are non-empty and unique within their files.
- lottery is an integer, unique across applicants.
- capacity is a non-negative integer.
- Ranks are integers starting at 1, with no gaps or duplicates within one list.
- Every program\_id in applicant\_rankings.csv exists in programs.csv, and every applicant\_id in program\_rankings.csv exists in applicants.csv.

Zero-capacity programs, applicants with empty lists, programs no one ranks, and more seats than applicants are all valid inputs.

### Acceptable pairs and blocking pairs

A pair is acceptable only when each side lists the other. An applicant and a program form a blocking pair when all three conditions hold:

1. The pair is acceptable.
2. The applicant is unmatched, or the applicant ranks the program above their current program.
3. The program has a free seat, or it ranks the applicant above its lowest-ranked held applicant.

The stability check tests every acceptable pair against this definition. The brute-force tests use the same definition.

### Output schemas

All CSV files use UTF-8, LF line endings, a header row, and no index column. Empty fields are blank.

- matches.csv has the columns applicant\_id, program\_id, applicant\_rank, and program\_rank, sorted by applicant\_id. Unmatched applicants have blank program\_id, applicant\_rank, and program\_rank.
- program\_summary.csv has the columns program\_id, capacity, filled, and unfilled, sorted by program\_id.
- validation.csv has the columns check, result, and detail. Each check gets one PASS or FAIL row. Each blocking pair found gets an extra row with check set to Stability, result set to FAIL, and detail set to the applicant and program IDs.

### Metadata

The generate command writes run\_metadata.json to the data directory. It records the seed, the generator parameters, a timestamp, and the Python, NumPy, and pandas versions. The match command writes run\_metadata.json to the results directory. It records the input directory, a timestamp, the versions, and the seed copied from the input metadata if that file exists, or null if it does not.

### Exit codes

| Code | Meaning | Outputs written |
| --- | --- | --- |
| 0 | Success, and all validation checks pass | Yes |
| 1 | A validation check failed | Yes |
| 2 | Input error | No |
| 3 | Usage error, such as a bad flag | No |

### Reproducibility and environment

Mock data is drawn with numpy.random.default\_rng(seed). Results are reproducible for the NumPy version pinned in pyproject.toml. Changing that version requires regenerating the expected results in the tests. The project targets Python 3.13.6, with all dependencies pinned in pyproject.toml, and is installed into a virtual environment.

## Code structure

The domain classes hold data and rules, with no file or console code. Dataclasses are frozen with `slots=True`. The design uses composition throughout, and inheritance appears only in the exception hierarchy. Dependencies such as the random generator, the console, and output paths are passed in rather than created inside classes. All code is fully type-hinted and checked with mypy in strict mode, and Ruff handles linting and formatting.

| Class | Module | Responsibility |
| --- | --- | --- |
| Applicant, Program, Match, ValidationIssue, GeneratorConfig | models.py | Frozen dataclasses that hold data |
| Market | market.py | Immutable problem with applicants, programs, both rankings, precomputed rank lookups, and the acceptable-pair test |
| Matching | matching.py | Immutable result with holder lookups in both directions |
| DeferredAcceptance | matching.py | Runs resident-proposing deferred acceptance with private state, and run() returns a Matching |
| Check | checks.py | typing.Protocol with run(market, matching) returning a list of ValidationIssue |
| CapacityCheck, SingleMatchCheck, ListedPairsCheck, StabilityCheck | checks.py | One check each, implementing Check |
| Validator | checks.py | Runs an ordered list of checks and collects their issues |
| CsvMarketLoader | io.py | Reads and validates the four input files, returning a Market or raising InputError |
| CsvResultWriter | io.py | Writes the matches, program summary, validation, and metadata files |
| MockGenerator | generate.py | Builds a Market from a GeneratorConfig and an injected NumPy generator |
| ConsoleReporter | console.py | Rich-based display with one method per section |

The exception hierarchy lives in errors.py. ResidencyMatchError is the base class. InputError carries the list of issues and maps to exit status 2, and UsageError maps to exit status 3.

### Documentation standards

The code is written to be read by someone new to the project. Documentation is part of each change, not a later task.

- Every module opens with a module docstring that states its purpose and what it deliberately does not do. For example, models.py does no file or console I/O.
- Every class has a docstring that describes its responsibility, lists its attributes or fields, and states any invariants it guarantees. Classes with non-obvious usage include a short example.
- Every public function and method has a NumPy-style docstring with Parameters, Returns, and Raises sections where they apply.
- Private helpers have a one-line docstring at minimum.
- Comments explain why the code does something, not what it does. The comments are dense in the places that are hardest to follow: the deferred acceptance loop, the blocking pair test, the rank conventions, and the lottery tie-break.
- Every test has a docstring that names the property or behavior it checks.
- A comment or docstring that no longer matches the code is a defect. It is updated in the same change as the code.

Ruff's pydocstyle rules enforce the presence of docstrings, so a missing docstring fails the lint step. The NumPy docstring convention is used throughout, which fits the rest of the data science stack.

## Build plan

Implementation proceeds in twelve steps. Implementation runs without pausing for review or approval. For each step, the work is: summarize the step, implement it, summarize what was built along with any issues or notes, update this spec with the completion date and implementation details, and commit to git with an informative message. Step 13 produces the user guide and the README. Step 1 also initializes the repository. Steps 4 and 5 are verification gates, where the core logic must pass its tests before anything depends on it.

- [x] 1\. (Done 2026-11-15: pyproject with exact pins, requirements.txt from pip freeze, .venv on 3.13.6, Ruff numpy-docstring rules, mypy strict, pandas-stubs added as dev dependency for strict typing; install, lint, type check and test all pass.) Project scaffold: pyproject.toml with pinned versions, a requirements.txt that documents every installed package, a .gitignore suited to this Python project, Ruff and mypy configuration, an empty package, and pytest. Done when install, lint, type check, and an empty test run all pass.
- [x] 2\. (Done 2026-11-15: errors.py (ResidencyMatchError, InputError exit 2, UsageError exit 3) and models.py frozen slotted dataclasses with invariants; ValidationIssue carries source, detail, optional row; errors.py imports models only under TYPE_CHECKING to avoid a cycle; 7 tests.) errors.py and models.py. Done when the dataclass invariants and exception classes have tests.
- [x] 3\. (Done 2026-11-15: market.py Market: frozen slotted dataclass with a custom __init__ that validates ids and lists, stores read-only lists and precomputed 1-based rank lookups, and exposes capacity, lottery, applicant_rank, program_rank, is_acceptable and acceptable_pairs; 10 tests.) market.py. Done when rank lookups and the acceptable-pair test are correct on hand-built markets.
- [x] 4\. (Done 2026-11-15: matching.py Matching (sorted pairs, lookups both ways, to_matches) and DeferredAcceptance (per-run private state, round callback, ranked by program rank then lottery). Gate passed: known answers plus a Hypothesis brute-force oracle in tests/helpers.py confirming the result is the applicant-optimal stable matching on markets up to 4x4, and feasibility/stability properties up to 8x5; 28 tests pass.) matching.py: Matching, then DeferredAcceptance. Done when textbook examples match and brute-force stable matchings agree on small random cases. Verification gate: tests must pass before continuing.
- [x] 5\. (Done 2026-11-15: checks.py Check protocol, CapacityCheck, SingleMatchCheck, ListedPairsCheck, StabilityCheck, Validator, plus two additions the spec implied: ReproducibilityCheck (re-runs DA on the same Market) and CheckResult (per-check outcome so the writer can emit one PASS/FAIL row per check). Matching no longer rejects duplicate applicants, so SingleMatchCheck can detect them independently. Gate passed: each check fails on a deliberately broken matching and StabilityCheck equals the brute-force oracle on every feasible matching; 36 tests pass.) checks.py: the four checks and the Validator. Done when each check fails on a deliberately broken matching and StabilityCheck agrees with brute force. Verification gate: tests must pass before continuing.
- [x] 6\. (Done 2026-11-15: io.py CsvMarketLoader reads each file as text with pandas, collects every issue across all four files (file name and one-based data row), then raises InputError or returns a Market; cross-reference sets come from raw id columns so one bad row does not cause follow-on errors; 13 fixture tests, one per rule.) io.py loader. Done when each validation rule has a fixture that produces the expected issue.
- [x] 7\. (Done 2026-11-15: io.py CsvResultWriter (matches, program summary, validation, match metadata), plus CsvMarketWriter for the generator, write_metadata, read_seed and environment_versions; all cells written as text so blanks stay blank; golden byte tests for column order, blanks, LF and UTF-8; validation.csv writes an extra FAIL row for every problem of any failing check, not only Stability. Timestamp is injected for deterministic tests.) io.py writer and metadata. Done when golden-file tests confirm column order, blank fields, and encoding.
- [x] 8\. (Done 2026-11-15: generate.py MockGenerator (injected NumPy rng, fixed draw order, ids A001../P01.., list lengths clamped) and generate_files, which writes the files, reloads them with the match-time loader, then writes run_metadata.json with seed, parameters, effective lengths, timestamp and versions; same seed gives byte-identical files; Hypothesis round-trip test; 10 tests.) generate.py. Done when the same seed gives identical files and the generated output passes the loader and validator.
- [x] 9\. (Done 2026-11-15: console.py ConsoleReporter with one method per section (header, inputs_summary, progress spinner callback, matches_table, programs_table, validation_panel, input_errors, footer) on an injected Rich Console; quiet mode prints only the footer; input errors go to stderr; fill bar uses ASCII so logs stay readable; 10 tests assert the text of each section and the green/red styling.) console.py. Done when tests confirm the text of each section.
- [x] 10\. (Done 2026-11-15: cli.py main() with injected console, prompts, clock and interactivity; argparse errors become UsageError (exit 3); required flags are prompted on a terminal and listed in an error when not; overwrite of a non-empty generate directory needs --force or a confirmation; InputError gives exit 2 with nothing written; failed validation gives exit 1 after writing outputs. Added a --force flag, which the spec did not name. Subprocess tests cover exits 0, 2, 3; exit 1 is tested in-process with a broken matcher because the real matcher cannot fail; 13 tests.) cli.py and **main**.py. Done when subprocess tests confirm exit codes 0, 1, 2, and 3 and the prompt rules.
- [x] 11\. (Done 2026-11-15: tests/test_end_to_end.py: Hypothesis runs random generated markets (including empty and zero-capacity) through generate, load, match, validate and write with every check passing; in-process CLI runs over arbitrary seeds exit 0; same seed gives identical matches; a 200x20 market passes; seed flows from generate metadata to match metadata (null when absent); oracle agreement re-checked end to end. 95 tests total.) End-to-end and property tests. Done when random markets pass the full pipeline with no failures.
- [x] 12\. (Done 2026-11-15: reviewed every module for docstring accuracy against the final code; Ruff pydocstyle (numpy convention) is clean over package and tests; pytest now also runs the docstring examples (--doctest-modules) so stale examples fail the build; 6 doctests pass.) Documentation pass. Done when docstring lint is clean across every module.
- [x] 13\. (Done 2026-11-15: README.md (features, install, quick start, exit codes, development, layout) and USER_GUIDE.md (all flags, prompt rules, file formats, outputs, console display, exit codes, 12 features to test), with commands and output checked against a real run.) User guide and README. Generate a user guide that explains how to use the program and highlights features to test, and generate a README.md suitable for the git repository. Done when both files are committed and reviewed.

## Future work

These features are out of scope for version 1, roughly in the order they would likely be added:

- Score-based program rankings, with the lottery applied to tied scores.
- A generative model that builds program rankings from applicant attributes, with interview noise.
- Monte Carlo runs that report distributions of outcomes instead of a single matching.
- Sensitivity analysis, such as how the match changes when one capacity moves by one.
- Per-track and per-specialty quotas, including minimum quotas, with stability caveats reported.
- Couples, which need a procedure that handles joint applications.
- A second round that fills unfilled seats.
- A switch to program-proposing deferred acceptance for side-by-side comparison.
- Import adapters for real rank-list and score data.
- A schema file for input validation, shared by the generator and the matcher.
- Plots of outcome distributions, built with the same stack.

## Decisions from the input discussion

These decisions are settled for version 1.

- Input layout: four separate CSV files, one per record type.
- Program rankings: strict orders only in version 1. Score-based input with ties is future work.
- Mock data defaults: capacity 2 to 6 per program, and each applicant ranks 5 programs.
- Exit status: the match command writes all output files, then exits nonzero if any validation check fails.
- Reproducibility check: the validator re-runs deferred acceptance on the same loaded Market and compares the two matchings. It does not need a seed, so it works whether or not run\_metadata.json exists.
- Git: step 1 initializes the repository, and each step is committed with an informative message. Keith Dowd is the only commit author. Commit messages carry no tool or co-author attribution. There is no remote and nothing is pushed.
- Generator list lengths: if applicant\_list\_length exceeds the number of programs, or program\_list\_length exceeds the number of applicants, the generator clamps to the available count. The effective values are recorded in run\_metadata.json.
- Dependency pinning: create a virtual environment with Python 3.13.6, install the latest releases of every package, and pin the exact installed versions with == in pyproject.toml and requirements.txt.
