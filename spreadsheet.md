# Spreadsheet Result Logging

Use this guide when the user asks to put WandB or job results into a shared
experiment spreadsheet. Inspect the live workbook before trusting a saved tab
name or row number.

## Which Workbook

| Project | Spreadsheet | Tab |
|---|---|---|
| VLM (PaliGemma / JAX LLaVA) | `1FlcygQbGBTqHLJeiKdwxS0nP41SPMJrtX-kCJq8d7SQ` | cleaned PaliGemma/JAX LLaVA tab |
| `EqR` / `EqR-jax` | `17pvrMbOKOKFiIa-eorO8Od12qc5JmrFCSXcXKeoe_u0` | `EqR-reproduction` (gid 1739404389) |

Read and write with the `gsheets` CLI
(`/google/bin/releases/gemini-agents-gsheets/gsheets`); never scrape the URL.
See the `gsheets` skill.

## What Must Be Logged

Every experiment that produces a **conclusion** goes in the sheet. A run that
only exposed a code bug, a packaging failure, or an infra preemption does not:
those belong in the commit message or the project guide, not the results table.

Each logged row must carry the **XM chart link**, not only the XID. See
§Chart Links below for where it comes from, and §Provenance for the fields the
chart link does NOT contain and must therefore be recorded separately.

## Row Shape

A published/reference number and a run of ours are DIFFERENT ROWS. Give each
dataset an `official baseline` row holding the paper's or upstream README's
numbers, then put our runs under it. Do not restate the reference inside a run's
cells — a number that appears twice will eventually disagree with itself.
The run row says only whether it matches, and by how much.

## Core Rule

Do not write when the run and sheet are not directly comparable. Stop and report
the discrepancy if a metric is missing or renamed, uses a different split or
protocol, final evaluations disagree, training continuity is unexplained, the
target cells conflict, or the task would require cross-region benchmark or
checkpoint access.

The user should decide how to represent an out-of-distribution result. An agent
must not silently force it into the existing schema.

## Transaction

1. Resolve the input to an exact WandB run and, when relevant, an exact job
   attempt.
2. Read the nearby sheet rows before choosing a target. Reuse a clearly matching
   blank row or insert beside the closest comparable experiment, not at the end
   by default.
3. Pull identity, config, final metrics, and step/loss continuity from WandB and
   logs. Do not scan benchmark datasets merely to fill a diagnostic.
4. Normalize only metrics whose semantics are known, then run the comparability
   hard stop above.
5. Write the smallest range, preserve the WandB link, apply only intentional
   formatting, and read back values, formulas, and colors.
6. Report the changed row, run id/name, missing diagnostics, and any caveat.

## Semantics That Must Stay Explicit

- **EqR-jax eval metrics are reported over PADDED rows; correct them first.**
  The maze test split is 1000 puzzles but a `512 x 2` eval feeds 1024 rows, and
  `puzzle_dataset._collate_batch` pads with `labels = IGNORE_LABEL_ID`. In
  `eval_fn._exact_matrix`, `exact = ((pred == labels) | ~mask).all(-1)` — a pad
  row has `~mask` everywhere, so it counts as CORRECT for every replica. Every
  `different_init/*`, `majority_vote/*` and `convergence_top_k/*` figure is
  therefore inflated; divide by the fed row count, not the real one.
  `all/exact_accuracy` from the loss head is NOT affected (it gates on
  `valid = loss_counts > 0`, which is false for pads).

  Correct with `(reported * rows_fed - pad_rows) / real_rows`. Log the corrected
  value and say so in Notes. Two checks that settle any dispute: the corrected
  `different_init/avg_pass_rate` must equal `all/exact_accuracy` exactly (both
  measure single-replica exact accuracy), and `reported * rows_fed` must be an
  integer count. For XID 275709629 that is `(0.8258056640625*1024 - 24)/1000 =
  0.821625 = all/exact_accuracy`, bit-exact.

  When `rows_fed == total_samples` there is no padding and no correction (e.g.
  the sudoku 2048-sample evals, where `avg_pass_rate == all/exact_accuracy`
  already).

- Use stage-1 final metrics for pretraining rows and stage-2 final metrics for
  SFT rows. Represent a pretrain/SFT pair as adjacent rows even if one WandB run
  contains both stages.
- The main POPE column is adversarial F1, not macro F1.
- ImageNet KNN protocols such as raw and PCA-whitened are not interchangeable.
- Greedy and beam-search VStar/VisWiz values are not interchangeable.
- MMVP uses the official 150-pair both-correct accuracy, not 300-item accuracy.
  Its random-choice baseline is `25%`: mark a comparable post-fix score red
  only when it is strictly below `25%`. Keep legacy item-accuracy results
  purple as protocol-invalid rather than applying the red threshold to them.
- The cleaned tab places CVBench in `W`, VLMs Are Blind in `X`, WandB/run in
  `Y`, and the legacy 15-benchmark composite in `Z`. CVBench uses the official
  source-balanced score with a protocol-aligned random-choice floor of
  `42.4889%` (displayed `42.49`). VLMs Are Blind uses the official eight-task
  mean and its published uniform-random floor of `24.00%`. Mark comparable
  values red only when they are strictly below their respective floors.
- RefCOCOg valid-answer count is a diagnostic placed in the note when already
  logged; write `n/a` rather than opening result data solely to compute it.
- Label cells `A:D` are red only for a verified encoder misconfiguration. Metric
  cells `F:X` use a separate below-trivial-score signal. Inserting a row can
  inherit both formats, so clear inherited backgrounds before reapplying either.

For bulk reformatting or structural cleanup, duplicate the worksheet first
unless the user explicitly authorizes changing the original. Historical column
maps, thresholds, and API snippets are in `archive/details/` if the live sheet
alone is insufficient.

## Chart Links

A Borg/XManager job has no WandB run, so "the chart" is a different URL per
backend. Resolve which one the job actually wrote before pasting a link; a URL
that renders an empty page is worse than no link.

| Link | What it shows |
|---|---|
| `http://flatboard/xid/<XID>` | the metric **curves** — this is the chart link to log |
| `http://datatable/xid/<XID>/data` | the raw scalar table behind those curves |
| `http://xids/<XID>` | the XManager experiment page (status, work units, config) |

`EqR-jax` routes `wandb.log()` to DeepMind **Datatables** through
`clu.metric_writers` (`utils/wandb_util.py::log_metrics`), keyed by `$XM_XID` /
`$XM_WID`, which the Borg template injects. Verify the run really wrote metrics
before trusting the link:

- The writer logs `Datatables metric writer ready` on rank 0 at startup. A
  `Could not start the Datatables writer` or `metrics stay log-only` warning
  means the curves do not exist and only the job log has numbers.
- `write_to_datatable=True` must be explicit. The default (`None`) ACL-gates on
  `mdb/datatables-users` and silently writes **nothing**, with no error.
- `write_to_xm_measurements=False` on purpose: XM Measurements is deprecated and
  drops anything past 1 point/sec/label. Do not log an `xm measurements` link.
- An `eval_only` job that finishes in seconds may never reach the flush
  threshold. Its durable evidence is the metrics CSV/JSON under the checkpoint
  bucket's `eval/eval_preds/`, so log that path alongside the chart link.

## Provenance: What The Chart Link Does Not Carry

A chart link resolves to **metrics only**. It does not identify the code that
produced them. `logdir` and `stagedir` are written by `xm_launcher.py` into
`~/.tpu_jobs.json`, keyed by XID — they never reach Datatables, Flatboard, or
the XM experiment page. So a row with only a chart link cannot answer "which
source snapshot was this?", which is exactly the question a reproduction table
exists to answer.

Record these alongside the chart link:

| Field | Source | Why it is not recoverable from the chart |
|---|---|---|
| `stagedir` | `~/.tpu_jobs.json[xid].stagedir` | The immutable CitC snapshot that was packaged. The home checkout has moved on since; this is the only pointer to the exact code. |
| `logdir` | `~/.tpu_jobs.json[xid].logdir` | Holds `xm_launch.log`, i.e. the launch command, resolved flags, and allocator verdict. |
| eval outputs | `~/.tpu_jobs.json[xid].bucket_cp_path` + `/eval/eval_preds/` | The per-sweep-point metrics CSV/JSON and `eval_config.json`. Survives when Datatables has nothing (short jobs) and records the FULLY RESOLVED config, including arch merged from the checkpoint. |

Pull all three at once:

```bash
python3 -c "import json; e=json.load(open('$HOME/.tpu_jobs.json'))['<XID>'];
print(e['stagedir']); print(e['logdir']); print(e['bucket_cp_path'])"
```

`tpu clear` archives entries into `~/.tpu_jobs_legacy.json` rather than deleting
them, so an old XID is still resolvable there — but it is a local file on one
workstation, which is a second reason to copy these fields into the sheet.
