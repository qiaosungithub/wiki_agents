# VLM Benchmark Metrics

Owns which number each VLM benchmark name means, the trivial floor it is judged
against, the composite score in `Z`, and what each background colour means on the
VLM tab. Writing a row is `spreadsheet.md`; benchmark data, splits, and scorers are
`vlm_data.md`. Read this page before a VLM result reaches the spreadsheet, and
whenever a benchmark number looks wrong.

Chapter 1 is what each score means, its floor, and the composite in `Z`; Chapter 2
is what each colour means.

---

## Chapter 1 — What Each Score Means

### The number that counts

**Report the variant named here, because another variant of the same benchmark
is a different number, not a rounding of this one.** A pretraining row takes
stage-1 final metrics and an SFT row takes stage-2 final metrics
(`spreadsheet.md` §Choose the row before the values).

| Benchmark | The number that counts | Trivial floor |
|---|---|---|
| POPE | Adversarial F1, not macro F1 | `66.67%`, the F1 of always answering yes |
| MMVP | Official 150-pair both-correct accuracy, not 300-item accuracy | `25%`, random choice |
| CVBench | Official source-balanced score | `42.4889%`, the protocol-aligned random-choice floor, displayed `42.49` |
| VLMs Are Blind | Official eight-task mean | `24.00%`, the published uniform-random floor |
| ImageNet KNN | Raw and PCA-whitened KNN are separate protocols, so never mix them in one column | `0.1%`, random top-1 over 1000 classes |
| VStar/VisWiz | Greedy and beam-search values are separate protocols, so never mix them in one column | VStar `25%`, four-way random choice; VisWiz `0` |
| DocVQA | ANLS as defined in `vlm_data.md` §Final-eval benchmarks | None, because the VLM tab has no DocVQA column |

- Stage-3 training in `PaliGemma-baseline` and `beifen-Paligemma` includes `docvqa_train` through the grouped LLaVA-OV1.5 stream. A Stage-3 DocVQA score is therefore in-domain supervised evaluation, not zero-shot document understanding.

### Floors are protocol-specific

**Mark a comparable metric value red only when it is strictly below the floor of
its own protocol, so a value equal to the floor is not marked.**

- A floor borrowed from another variant of the benchmark raises false alarms, so each variant keeps its own.
- A result under a superseded protocol, such as legacy MMVP item accuracy, is marked purple as protocol-invalid and never judged against a floor (Chapter 2).
- The `MME-P / MME-S` cell is marked when either part is strictly below `750 / 1050`: random 50% accuracy plus 25% accuracy-plus per task, summed over the 10 perception tasks and all 14 tasks.
- A cognition score, `MME-S − MME-P`, under `300` does not mark the MME cell by itself.
- Floors not listed in §The number that counts are in the tab's trivial-floor reference row.
- Historical thresholds and column maps are in `archive/details/spreadsheet_logging_playbook.md`, for when the live sheet alone is insufficient. Its MMVP floor of `50` belongs to the superseded item-accuracy protocol.

### Where the columns are

**Build the column map from the live header before every write
(`spreadsheet.md` §Re-read the header every time); the layout below only helps
you recognise the cleaned tab.** There, CVBench is in `W`, VLMs Are Blind is in
`X`, and the `WandB / run` link is in `Y`. `Z` holds a hand-typed composite score
(§The composite score in Z).

### The composite score in Z

**`Z` is typed by hand, not computed by a sheet formula, and the column holds two
definitions, so compare two `Z` values only when both use the same one.** Each
item is its score raised to that item's floor, `max(score, floor)`, and `Z` is the
plain mean of the items.

| Definition | Items, each at its floor | Where it appears |
|---|---|---|
| 13 items | MME perception `MME-P / 2000 × 100` and MME cognition `(MME-S − MME-P) / 800 × 100`, both at `37.5`. VQAv2, TextVQA, RefCOCOg, OCRBench, and GQA at `0`; MMBench, VStar, MMVP, and SEED-Bench at `25`; POPE at `66.67`; CountBench at `10` | Purple `Z` cells in rows with no VisWiz or ScienceQA-IMG score |
| 15 items | The 13 items plus VisWiz at `0` and ScienceQA-IMG at `20`, with MMVP at `50` instead of `25` | Every white `Z` cell. The note on the reference row's `Z` cell describes only this definition |

- A purple `Z` never compares with a white one. Besides the 13-item rows, purple marks a 15-item `Z` that clamps MMVP at `25` or includes an item scored under a different protocol.
- Give a new row's `Z` the definition and background of its parent row. A new family without VisWiz and ScienceQA-IMG scores uses the 13 items.
- The Z delta in a note is the row's `Z` minus its parent row's `Z` (`spreadsheet.md` §Note (B) style).
- ImageNet KNN, CVBench, and VLMs Are Blind are in neither definition.

### RefCOCOg valid answers

**The RefCOCOg valid-answer count is a note diagnostic, not a score: record it
when WandB or the output log already has it, and write `n/a` otherwise.** Never
open result data solely to compute it.

```text
RefCOCOg valid ans: 1383/7573 (18.26%).
RefCOCOg valid ans: n/a (not logged).
```

---

## Chapter 2 — What Each Colour Means

### The colour legend

**This table is the only definition of a background colour on the VLM tab, so
read it before applying a colour and add a row here before taking a free one.**
A colour applied loosely stops meaning anything for every row that used it
correctly.

| Colour | Scope | Meaning |
|---|---|---|
| `#F4CCCC` light red | One metric cell in `F:X` | The value is strictly below that benchmark's own trivial floor. Older rows use `#F4B7B2`, `#FFCCCC`, or `#F3CCCC` for the same meaning; write `#F4CCCC` |
| `#F4CCCC` light red | Label cells `A:D` | A verified encoder misconfiguration (§Label red means a wrong encoder) |
| `#D9D2E9` purple | One metric cell, or `Z` | In a metric cell, a different protocol for the same benchmark, such as MMVP scored as 300-item accuracy instead of the official 150-pair score. In `Z`, a composite not comparable with white `Z` cells (§The composite score in Z) |
| `#CCEFCC` green | The Note (B) cell | The freeze configuration matches original LLaVA stage 2 ("FREEZE OK") |
| `#FFE2A5` amber | The Note (B) cell | A freeze ablation that deliberately departs from the reference freeze configuration |
| `#D0E2F3` light blue | The `WandB / run` cell only | The job ran through XManager |
| `#C6DBF9` blue, `#E0EAF4` pale blue, `#FFF2BF` yellow | Whole row | Structure: the header row, a block header, and the trivial-floor reference row |

The legend is the rule for new cells, and older rows do not all follow it. Some
older cells are red without being below their floor, some are below it and still
white, and some reds cover a whole early row or a `WandB / run` cell. Judge each
new value against its floor, never against a neighbouring cell's colour.

### Scope a signal to the cell it describes

**Put a job-level signal on the identity column and a value-level signal on the
metric cell, so two true statements never compete for one background.** Red is
about a number, blue is about the run that produced it, and `WandB / run` already
identifies the run.

### Label red means a wrong encoder

**Colour label cells `A:D` red only after verifying the encoder misconfiguration
from the run config or `output.log`; this signal is separate from the below-floor
reds in `F:X`.**

- The misconfiguration it marks is a run intended as encoder "426" (`enc_num_patch_sa_layers=4`, `enc_num_cross_attn_layers=2`, `enc_num_token_sa_layers=6`) that actually ran as "420", with `enc_num_token_sa_layers=0`.
- A `[wrong config]` block has `A:D` red on every stage row, and a correctly configured run keeps `A:D` white.
- Inserting a row inherits both the label and the metric backgrounds, so clear both before reapplying either (`spreadsheet.md` §An inserted row inherits formatting).
- In a Sheets API request the two label backgrounds are written as below, and `red` equals `#F4CCCC`.

```python
red = {"red": 0.95686275, "green": 0.8, "blue": 0.8}
white = {"red": 1, "green": 1, "blue": 1}
```

### Read a colour back

**Verify every colour write by reading it back, which also shows every colour in
use and whether one is free before you claim it.** The reading method and its
traps are `spreadsheet.md` §A colour check that cannot fail.
