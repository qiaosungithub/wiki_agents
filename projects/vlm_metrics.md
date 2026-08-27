# VLM Benchmark Reporting

Read this before a VLM result reaches the shared spreadsheet, or when a
benchmark number looks wrong. This file owns *which number* each benchmark name
means; `../research/result_logging.md` owns the write mechanics, the "settle the
protocol first" rule, and every column map — rebuild that map from the live
header each time rather than from either file.

## One Benchmark Name, Several Numbers

**Report the variant named here; the alternatives are different numbers, not
rounding.** Pretraining rows take stage-1 final metrics and SFT rows stage-2
final metrics, as two adjacent rows even when one run covers both stages.

| Benchmark | The number that counts | Trivial floor |
|---|---|---|
| POPE | **adversarial F1**, not macro F1 | — |
| MMVP | official 150-pair both-correct accuracy, not 300-item | `25%` |
| CVBench | official source-balanced score | `42.4889%` protocol-aligned, displayed `42.49` |
| VLMs Are Blind | official eight-task mean | `24.00%` published uniform-random |
| ImageNet KNN | raw and PCA-whitened are separate protocols | — |
| VStar / VisWiz | greedy and beam-search are separate protocols | — |
| DocVQA | ANLS per `vlm_data.md`; Stage-3 training already includes DocVQA-train through the OV1.5 grouped stream, so this is in-domain supervised evaluation, **never zero-shot document generalization** | — |
| RefCOCOg valid answers | a diagnostic: note it when already logged, else `n/a`; never open result data solely to compute it | — |

**Red on a metric means strictly below its OWN floor above** — each follows from
its benchmark's protocol, so one borrowed from a neighbour raises false alarms —
while **red on a label means a verified encoder misconfiguration.** Two
different signals; inserting a row inherits both, so clear inherited backgrounds
before reapplying either. A result produced under a superseded protocol is
marked protocol-invalid instead, never scored against a floor.

## The Colour Table Of The VLM Tab

**This file is the canonical owner of what a background colour means on the
VLM tab**; `../research/result_logging.md` owns the write mechanics and the
"clear inherited formatting first" rule. **Read this table before applying any
colour, and never take a free one without adding it here** — a colour applied
loosely destroys it for every row that used it correctly.

| Colour | Scope | Meaning |
|---|---|---|
| `#F4CCCC` light red | one metric cell | value strictly below that benchmark's own trivial floor |
| `#F4CCCC` light red | a label cell | verified encoder misconfiguration |
| `#D9D2E9` purple | one metric cell | a **different protocol** for the same benchmark (e.g. MMVP scored on the 300-item variant instead of the official 150-pair) |
| `#CCEFCC` green | the `Note` cell | freeze configuration matches original LLaVA stage-2 ("FREEZE OK") |
| `#FFE2A5` amber | the `Note` cell | freeze **ablation**: deliberately not the reference freeze config |
| `#D0E2F3` light blue | the `WandB / run` cell only | the job was run through xm/XManager |
| `#C6DBF9` blue, `#E0EAF4` pale blue, `#FFF2BF` yellow | whole row | structure: header row, block header, and the trivial-floor reference row |

**Scope the job-level signals to the identity column and the value-level
signals to the metric cell**, so two true statements never contend for one
background: red says something about a number, blue says something about the
run that produced it, and `WandB / run` is the cell that already identifies the
run. Verify a colour by reading it back — exporting the workbook to xlsx and
resolving each cell's `fillId` against `styles.xml` shows every colour actually
in use, which is how you check a colour is free before claiming it.
