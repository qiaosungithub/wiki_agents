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

**A train run and its eval are also different rows, paired.** The train row
carries the training evidence (final losses, final train accuracies, the
tail-window mean, steps completed); the eval row directly beneath it, titled
`  ↳ eval of the row above`, carries the paper-protocol accuracies. They have
different XIDs, different configs and different failure modes, so collapsing
them loses the ability to say *which half* went wrong. A train row with no eval
row yet is a run whose conclusion does not exist — mark it, do not quote its
in-training numbers as results.

**Name the ablation axis in the first line of `Notes`, as `- <feature>`, and
name the row it is measured against.** `- attention (mlp_t=false) instead of
MLP-T, vs the full-corpus rope pair above` is a complete description; "attention
variant" is not. Without the comparison target a reader cannot tell a two-point
drop from a two-point win.

**Keep prose short and load-bearing.** Notes/Details exist to make the number
interpretable — protocol, sample count, what differs from the comparison row,
and any caveat that changes how much to trust it (a run that stopped short, a
padding correction applied). Explanations of *why* a bug happened belong in the
commit message, not the sheet.

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

## A Metric Is Not Comparable Until Its Protocol Is

The recurring failure is not a typo in a cell; it is two numbers that look alike
and mean different things. Before writing any value, settle:

- **What population it is computed over.** An evaluation that pads its input to
  a fixed batch shape reports over the padded rows, and padding can be scored as
  correct — inflating every derived figure while one unaffected metric quietly
  disagrees. Establish the real denominator, correct explicitly, and say in the
  notes that you did.
- **Whether it is a converged value or a single sample.** A "final" training
  metric is usually the one step that landed on the logging grid, carrying full
  batch-to-batch variance; two runs can differ by points purely from where they
  landed. Record a tail-window mean with its step range and compare runs on
  that.
- **Whether it was produced by the protocol you are claiming.** An in-training
  periodic evaluation runs at whatever depth, breadth, and sample count is cheap
  — it is a health signal, not a headline result. The paired evaluation row is
  the result.
- **Whether the run finished.** A run that stops just short of budget may simply
  have ended between log points; a run that stops well short was interrupted.
  Record steps completed and say which it was, because an evaluation of a short
  checkpoint is pessimistic and the row must admit it.
- **Which variant of a benchmark it is.** Averaging conventions, answer
  extraction, split, and scoring mode all produce different numbers under the
  same benchmark name, and they are never interchangeable. Each benchmark also
  has its own trivial-score floor — a threshold applied from the wrong protocol
  is a false alarm.

Two checks worth running whenever a corrected number is disputed: it should
agree exactly with an independent metric that measures the same thing by another
route, and multiplying by the population should give a whole count.

Project-specific metric semantics live with the project — see
`projects/eqr_jax.md` and `projects/vlm_metrics.md`.

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
