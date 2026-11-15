# Algorithm and Implementation Notes

This document explains how the residency match simulator computes a match, why
the result looks the way it does, and which other approaches could have been
used. It is written for a technical reader who has not met matching theory
before. For how to run the program, see [USER_GUIDE.md](USER_GUIDE.md); for the
original design and build log, see [SPEC.md](SPEC.md).

## 1. Overview

The program takes two sets of preferences and produces a match:

- Each **applicant** ranks the programs they would accept.
- Each **program** ranks the applicants it would accept and has a fixed number
  of seats (its capacity).

The matcher uses **resident-proposing deferred acceptance**, usually called the
Gale-Shapley algorithm. Applicants propose, programs hold their best offers
tentatively, and the process repeats until nobody can improve. The result is a
**stable** matching that is the best stable outcome for every applicant at once.

Everything is deterministic. The same input files always give byte-identical
output files, and the same seed always generates the same input files.

## 2. The matching problem

### Acceptable pairs

A pair of applicant and program can match only if **both sides list each
other**. If an applicant lists a program that does not rank them, or a program
ranks an applicant who did not list it, that pair is unacceptable and can never
be matched. This is implemented in `Market.is_acceptable` (`market.py`).

### Ranks

Positions on a list are 1-based, and 1 is most preferred. The `Market` class
precomputes a lookup from each person to the rank of each listed partner, so
asking "how does this applicant rank that program" is a single dictionary read.
These ranks are what appear as `applicant_rank` and `program_rank` in
`matches.csv`.

### Stability

A matching is **stable** when no applicant and program would both rather be
matched to each other than to what they have. Such a pair is called a *blocking
pair*. The code uses this exact definition (`StabilityCheck` in `checks.py`). A
pair blocks when all three hold:

1. The pair is acceptable.
2. The applicant is unmatched, or ranks this program above their current one.
3. The program has a free seat, or ranks this applicant above the worst
   applicant it currently holds.

Stability matters because an unstable result invites side deals: the blocking
pair could walk away from the match and both be better off. Residency matching
has used stable algorithms for decades for this reason.

## 3. Deferred acceptance step by step

The implementation is `DeferredAcceptance` in `matching.py`. Each applicant has
a **pointer** into their own list, starting at their first choice. Each program
has a set of applicants it is **tentatively holding**, never more than its
capacity.

Each round:

1. Every applicant who is not currently held, and who still has programs left on
   their list, proposes to the program at their pointer.
2. Each program that received proposals looks at everyone it is holding plus
   the new proposers, ranks them, and keeps its best `capacity` applicants.
   Applicants it does not rank at all are always rejected, even if seats are
   empty.
3. Every applicant who was rejected, whether a new proposer turned away or a
   held applicant bumped by someone better, moves their pointer to the next
   program on their list. An applicant who runs out of programs stays
   unmatched.
4. The run ends in the first round where nobody proposes. The final holds are
   the matching.

The word *deferred* matters: a program's acceptance is never final until the
end. A hold is only a promise to keep the applicant unless someone better
arrives. That is what lets applicants safely propose to their favorite program
first without risking anything.

### A worked example

Four applicants (A, B, C, D) and two programs. Program X has 2 seats and
program Y has 1 seat. Lists, best first:

| | Ranks |
| --- | --- |
| Applicant A | X, Y |
| Applicant B | X, Y |
| Applicant C | X |
| Applicant D | Y, X |
| Program X (2 seats) | C, A, B, D |
| Program Y (1 seat) | B, D, A |

**Round 1.** A, B and C propose to X; D proposes to Y. X compares C (its rank
1), A (rank 2) and B (rank 3), and keeps C and A because it has two seats. B is
rejected and moves on to Y. Y has only D, so it holds D.

**Round 2.** B is the only applicant who is not held, so only B proposes, to Y.
Y compares B (its rank 1) with its current hold D (rank 2), keeps B, and
rejects D. This is the *displacement* that gives the algorithm its name: D had
a hold and lost it.

**Round 3.** D proposes to its next choice, X. X compares C, A and D, and D is
its lowest ranked of the three. D is rejected, and D has no programs left.

**Round 4.** Nobody proposes, so the run ends.

| Applicant | Program | Applicant rank | Program rank |
| --- | --- | --- | --- |
| A | X | 1 | 2 |
| B | Y | 2 | 1 |
| C | X | 1 | 1 |
| D | unmatched | | |

The proposals per round were 4, 1 and 1, which is what the progress spinner
shows while a run is in flight. This trace was produced by running the code on
exactly this instance, and you can verify there is no blocking pair: D would
accept X, but X prefers both of its current applicants to D.

## 4. Why the result looks the way it does

These are known properties of deferred acceptance, and they explain what you see
in `matches.csv`.

**Applicant-optimal.** Among all stable matchings, this one gives every
applicant the best program they could get in any stable outcome. No stable
matching exists in which some applicant does better. Programs get the opposite:
the worst stable outcome for programs.

**Strategy-proof for applicants.** An applicant can never get a better result by
listing programs in a different order than their true preference. Truthful
lists are the best strategy. This is why the algorithm is trusted for real
residency matches, and it is why applicants are the proposing side here. The
guarantee does not extend to programs, who can sometimes gain by misreporting
their rankings.

**The same applicants are matched in every stable matching.** A result known as
the rural hospitals theorem says the set of matched applicants, and the number
of filled seats at each program, is identical across all stable matchings. So
choices such as who proposes change *which* program a matched applicant gets,
but not *how many* applicants end up matched. Unmatched applicants are not an
artifact of this implementation.

**Effects of the inputs on the output:**

| Input feature | Effect on output |
| --- | --- |
| Program with zero capacity | Never holds anyone; shows `filled 0, unfilled 0` |
| More seats than ranked applicants | Seats stay unfilled; shown in `program_summary.csv` |
| Program does not rank an applicant | That applicant can never match there, even with free seats |
| Applicant with an empty list | Appears in `matches.csv` with blank program |
| Short applicant lists | Raise the chance of being unmatched |
| Strict (no-tie) program rankings | Lottery number is never consulted |

## 5. Implementation details and their effect on outputs

### Deterministic iteration

Applicants propose in the order they appear in `applicants.csv`, and a round's
proposals are grouped by program before each program decides. The stable
matching is the same whatever order proposals are processed in, but a fixed
order makes runs reproducible step by step. `Matching` stores its pairs sorted,
so equality checks and output file ordering never depend on dictionary order.

### The ranking key and the lottery

Inside `_consider`, applicants are sorted by `(program rank, lottery number)`.
With the strict rankings in version 1, the first element is never tied, so the
lottery number never decides anything. It is already wired in as the single
tie-break rule: if a future input gives programs scores with ties, the applicant
with the lower lottery number ranks higher. The loader also requires lottery
numbers to be unique so that the tie-break is itself never ambiguous.

### Immutable data

`Market` is frozen and builds its rank lookups once. Rank tests inside the
algorithm are constant time, and nothing in the matcher can accidentally change
the problem it is solving. `Matching` is also immutable. Each `DeferredAcceptance`
instance holds private mutable state for one run, so create a new one for each
run. That is why the reproducibility check builds a fresh instance.

### Progress callback

`run()` accepts an optional callback with the round number and proposal count.
The console spinner uses it. It is called after a round's decisions are made and
cannot influence them, so quiet and verbose runs give identical matches.

### Validation is independent of the matcher

The five checks (capacity, single match, listed pairs only, stability,
reproducibility) are written without calling the matcher's code, except that the
reproducibility check re-runs it on purpose. This is why a bug in the matcher can
fail a check instead of passing silently. `Matching` deliberately does not reject
an applicant who appears twice, so `SingleMatchCheck` can see the problem. A
failed check gives exit status 1 and every output file is still written, so you
can inspect what went wrong. With the real matcher no check ever fails, which is
why the exit-1 test uses a deliberately broken stand-in.

### Mock data and its consequences

The generator draws uniformly: random capacities in a range, random permutations
for the lottery, random program subsets for each applicant, and random
applicant permutations for each program. These are placeholders, and they shape
the outputs more than you might expect.

With the defaults (20 applicants, 5 programs, each applicant ranking all 5, each
program ranking all 20, capacity 2-6), program preferences are completely
uncorrelated with each other and with applicant preferences. Across 200 default
seeds (0-199), the measured results were:

| Outcome | Result |
| --- | --- |
| Average seats offered | 20.5 for 20 applicants |
| Average applicants matched | 18.95 of 20 (about 5% unmatched) |
| Matched at their 1st choice | 62.9% of matches |
| Matched at their 2nd choice | 20.5% |
| 3rd, 4th, 5th choice | 8.9%, 4.6%, 3.0% |

The few unmatched applicants are mostly a seat-count effect: when the random
capacities sum to fewer than 20, someone must go unmatched whatever the
preferences are. Real data would be different, since real programs rank by shared
signals such as scores, so strong applicants would be contested by many programs
and weaker ones by few. That is the "generative model" listed under future work
in the spec.

List lengths larger than what exists are clamped, and the effective values are
recorded in `run_metadata.json`, so an over-long request never fails but is
visible afterward.

### Strict input validation

`CsvMarketLoader` reports every problem, with file and row, before any matching
happens: wrong columns, duplicate ids, bad numbers, rank gaps, and references to
unknown ids. A bad file exits with status 2 and writes nothing. This means the
matcher can assume a well-formed `Market`, and never needs defensive code. The
generator uses the same loader on its own output so a generator bug fails at
generation time.

### Output format choices

Output files use UTF-8 with LF endings and blank cells (not words like `NONE`)
for unmatched applicants, so they load cleanly in pandas or a spreadsheet.
Everything is written as text so pandas never guesses a type, which keeps
files byte-identical across runs and platforms. Timestamps are the only
non-reproducible field, and they appear only in `run_metadata.json`.

## 6. Complexity and scale

- **Proposals.** Each applicant proposes to each program on their list at most
  once, so the total number of proposals, and the number of rounds, is bounded by
  the total length of all applicant lists. The default is at most 100 proposals.
- **One decision.** A program sorts its holds plus new proposers, so each
  decision costs about *k* log *k* for *k* people, which stays small because
  holds never exceed capacity.
- **Stability check.** It tests every acceptable pair, and each test may scan the
  program's holders, so cost grows roughly with pairs times capacity. The spec
  calls this quadratic, which is fine at the target scale. The test suite runs
  a 200-applicant, 20-program market through every check quickly.

## 7. Other approaches that could have been taken

### Different matching mechanisms

| Approach | How it works | Trade-off | What would change in the outputs |
| --- | --- | --- | --- |
| **Program-proposing deferred acceptance** | Programs propose, applicants hold | Gives the program-optimal stable matching; applicants can then gain by misreporting | Same set of matched applicants, but usually worse ranks for applicants and better for programs. Listed as future work for side-by-side comparison. |
| **Serial dictatorship** | Applicants pick in a fixed order (for example by lottery) from what is left | Simple, strategy-proof and efficient, but ignores program preferences | Not stable; programs would take whoever picks first rather than their best choice. The lottery would decide outcomes directly. |
| **Boston (immediate acceptance) mechanism** | Acceptances at each round are final | Rewards gaming: ranking a safe choice first helps | Not stable and not strategy-proof; applicants' lists stop being their true preferences. |
| **Top trading cycles** | Applicants trade seats in cycles | Efficient and strategy-proof for applicants, but not stable | Program rankings act only as priorities, so blocking pairs can appear. |
| **Optimization (integer programming or max-weight matching)** | Choose the match with the best total score | Can maximize total welfare or fill the most seats, but may be unstable unless stability is a constraint | Possibly more matched applicants or a better average rank, at the cost of blocking pairs. |

### Different tie-breaking

The spec uses one global lottery number per applicant for every tie
(*single tie-breaking*). The alternative is a separate random order for each
program (*multiple tie-breaking*). Single tie-breaking is easier to explain and
audit, since one number tells you everything. The two rules differ in fairness
and efficiency properties, which the school-choice literature discusses at
length. This matters only once input
has ties, since version 1 rankings are strict.

### Harder settings that break the standard guarantees

Couples, minimum quotas, and per-track quotas, all in the spec's future work, can
mean that no stable matching exists or that the problem becomes much harder to
solve. The spec says such cases need extra procedures and stability caveats
reported rather than the plain algorithm. A second round to fill unfilled seats
is also outside what deferred acceptance guarantees.

### Implementation alternatives

| Choice made | Alternative | Why this choice |
| --- | --- | --- |
| Round-based proposals | One proposer at a time with a queue | Same final matching. Rounds give a natural progress display (proposals per round). |
| Sorting the pool per decision | A heap of held applicants per program | A heap is faster for large capacities. At this scale sorting is simpler and easier to read. |
| Plain Python loops | NumPy-vectorized rounds | Faster at very large scale, but harder to read and verify. The target is about 20 applicants. |
| Four long-format CSV files | One wide file with list columns, or Parquet, or a database | Long format avoids quoted lists in cells and loads easily in any tool. |
| Frozen dataclasses | Pydantic models | Dataclasses add no dependency. The loader already does explicit validation with file and row numbers. |
| Brute-force oracle in tests | A SAT or integer-programming checker | Brute force is easy to trust on 4x4 markets. A solver would be needed for larger exhaustive checks. |

## 8. How the tests verify the algorithm

- **Known answers.** Hand-checked instances, including one where a held
  applicant is displaced and one with a program that ranks nobody.
- **Brute force.** On random markets of up to 4 applicants and 4 programs,
  `tests/helpers.py` lists every feasible matching, keeps the stable ones, and
  confirms the algorithm returns the one that every applicant weakly prefers
  over all other stable matchings. The oracle shares no code with the matcher.
- **Properties.** On larger random markets, every result respects capacity and
  listings and has no blocking pair, and a fresh run reproduces it.
- **Cross-check.** `StabilityCheck` is compared with the oracle's blocking pairs
  on every feasible matching of random small markets, not just the matcher's
  output.
- **Pipeline.** Randomly generated data goes through generate, load, match,
  validate and write, and every check passes.

## 9. Further reading

- D. Gale and L. S. Shapley, "College Admissions and the Stability of Marriage",
  *American Mathematical Monthly*, 1962. The original algorithm.
- A. E. Roth, "The Evolution of the Labor Market for Medical Interns and
  Residents: A Case Study in Game Theory", *Journal of Political Economy*, 1984.
  How the same idea was already used by the US residency match.
- A. E. Roth and M. Sotomayor, *Two-Sided Matching: A Study in Game-Theoretic
  Modeling and Analysis*, Cambridge University Press, 1990. The standard
  reference for the properties in section 4, including the rural hospitals
  theorem.
