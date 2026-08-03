# Spreadsheet Result Logging

Logging a result into the shared experiment spreadsheet is a routine, frequent
task. It is also the easiest place to silently corrupt the record, because a
wrong column or a wrong row looks exactly like a right one. Read this before
every write.

Read and write with the `gsheets` CLI
(`/google/bin/releases/gemini-agents-gsheets/gsheets`); never scrape the URL.
See the `gsheets` skill.

## Which Workbook

| Project | Spreadsheet | Tab |
|---|---|---|
| VLM (PaliGemma / JAX LLaVA) | `1FlcygQbGBTqHLJeiKdwxS0nP41SPMJrtX-kCJq8d7SQ` | the cleaned PaliGemma/JAX LLaVA tab |
| `EqR` / `EqR-jax` | `17pvrMbOKOKFiIa-eorO8Od12qc5JmrFCSXcXKeoe_u0` | `EqR-reproduction` |

**A `gid` does not identify a tab.** These two workbooks each contain a tab with
the *same* gid, because one was copied from the other, and they hold completely
different experiments. Always resolve a link by listing the workbook's sheets
and matching the **title**, never by trusting a gid you have seen before.
Likewise, both workbooks carry dated backup tabs of the other project — landing
in one of those writes your result into a frozen snapshot nobody reads.

## Before You Write: Re-Read The Header, Every Time

**Never write from a remembered column map.** These are living documents: a
human adds a benchmark column, renames a metric, inserts a section, or
reorganizes a tab between one session and the next. A stale map does not error
out — it writes your number into the wrong benchmark's column, which is worse
than not logging at all.

Each time, in this order:

1. List the sheets and resolve the tab by title.
2. Read the header rows and build the column map **now**. Expect the header not
   to be row 1: these tabs open with a banner row (the base setting, the code
   under test) above the real header, and often a reference row (trivial or
   random-choice scores) directly below it. Header layout differs per tab — the
   two workbooks above do not share column meanings.
3. Read the neighborhood you intend to write into, so you see the local
   conventions before adding to them.
4. Write the smallest range, then read it back.

**The same rule applies to your own tooling.** Keeping a helper script for
reading metrics or formatting rows is worthwhile and encouraged — but the code
and the spreadsheet drift independently, and each can change without the other.
A helper must re-derive the column map from the live header on every run, never
hardcode one; and you must sanity-check its output against the sheet before
trusting a write. Treat a helper as a convenience, not as a source of truth.

## What Must Be Logged

Every experiment that produces a **conclusion** goes in the sheet. A run that
only exposed a code bug, a packaging failure, or an infra preemption does not:
those belong in the commit message or the project guide, not the results table.

Each logged row must carry the **chart link** (not only the job id) **and the
`logdir` / `stagedir` pointers**. The pointers matter more than any prose in the
row: they are what lets a future reader recover the exact code, command, and
resolved config, which is why the text columns can stay short. See §Chart Links
for where the link comes from and §Provenance for what it cannot tell you.

## Where The Row Goes

**Decide the row before you decide the values.** Appending at the end is almost
always wrong: it destroys the comparison that makes the number mean anything.
The tab is not a log, it is a set of ablation groups, and a reader navigates it
by adjacency.

The layout in use:

- **A group opens with a full baseline row** that spells out its whole
  configuration — the setting, the dataset/mix, and the details that stay fixed
  for everything under it. A short free-text line above a group (`prefix MAE
  experiments`) names the family; a blank row separates families.
- **Every variant of that baseline goes beneath it, in the same
  block**, and states only what CHANGED, written as `- <change>`. Real examples
  from the reference tab: `- finetune on VQA, lr 2e-5 wd0.02 cos decay`,
  `- only 128 tokens`, `- fix randomness`. The leading `- ` is what marks the
  row as a delta rather than a new configuration.
- **A delta row leaves the inherited columns empty.** The baseline row above
  carries the dataset/mix and shared details; repeating them invites the two
  copies to disagree later. Fill only the delta description and the metrics that
  this variant actually produced.
- **A delta is relative to the block's baseline, not to the row immediately
  above.** When a change stacks on another variant, say so in the text; a bare
  `- ` line is read as "baseline plus this one change".
- **Keep an ablation axis contiguous.** All the learning-rate variants sit
  together, all the token-count variants sit together. Inserting the new row
  next to its comparison target is the whole point — a variant filed at the
  bottom of the sheet cannot be compared with anything.
- A variant that changes enough to invalidate the comparison is **not** a delta
  row. Start a new baseline block with its full configuration.

So the placement decision is: identify which baseline this run varies, find that
block, and insert into it — reusing a clearly matching blank row if one is
already there. Only genuinely new work starts a new block.

## Row Shape

A published/reference number and a run of ours are DIFFERENT ROWS. Give each
dataset an `official baseline` row holding the paper's or upstream README's
numbers, then put our runs under it. Do not restate the reference inside a run's
cells — a number that appears twice will eventually disagree with itself. The
run row says only whether it matches, and by how much.

**A train run and its eval are also different rows, paired.** The train row
carries the training evidence (final losses, final train accuracies, the
tail-window mean, steps completed); the eval row directly beneath it, titled
`  ↳ eval of the row above`, carries the paper-protocol accuracies. They have
different job ids, different configs and different failure modes, so collapsing
them loses the ability to say *which half* went wrong. A train row with no eval
row yet is a run whose conclusion does not exist — mark it, do not quote its
in-training numbers as results.

**Name the ablation axis in the first line of `Notes`, as `- <feature>`, and
name the row it is measured against.** `- attention (mlp_t=false) instead of
MLP-T, vs the full-corpus rope pair above` is a complete description; "attention
variant" is not. Without the comparison target a reader cannot tell a two-point
drop from a two-point win.

**Keep prose short and load-bearing** — see §Write Short Cells, below.

## Write Short Cells

**Do not write essays in a spreadsheet.** A cell is not a place to explain, to
narrate, or to justify — it exists to let the next reader find and interpret the
number. Everything else is noise that pushes the metrics off screen and makes
the tab unreadable. This is the most common way these tabs decay.

The test for any sentence: *does a future reader need this to use the number?*
If they need it only to understand how the run got that way, it belongs in the
commit message, the project guide, or the log — not the sheet.

- **The pointer columns are what make brevity safe.** `logdir` and `stagedir`
  reconstruct everything: the exact code snapshot, the launch command, the
  resolved flags, the full config. Because they are recorded, the text columns
  do not have to be. **Filling them is higher priority than any prose** — a row
  with a terse setting plus a correct `stagedir` is complete; a row with three
  sentences and no pointer is not. §Provenance below covers where they come
  from and why the chart link cannot replace them.
- **Settings should be short.** In the reference tab a full baseline setting
  runs roughly 15–75 characters — `MAE-L + Base init, recon weight 1.0, muon
  lr2e-4` — and that is a whole configuration. Aim for that scale, not a
  paragraph.
- **A delta row must not restate the baseline's setting.** It says only what
  changed — `- only 128 tokens`, `- fix randomness` — and leaves the inherited
  columns empty. Re-describing the fixed axes in every variant is exactly the
  duplication that later disagrees with itself, and it buries the one thing the
  row is about.
- **Notes and Details carry only what changes interpretation**: the protocol,
  the sample count, what differs from the comparison row, and a caveat that
  changes how much to trust the number (the run stopped short; a padding
  correction was applied). One clause each is usually enough.
- **Never explain a bug in a cell.** Why something broke is commit-message
  material. The sheet records what the number means, not the story behind it.

## Formatting Is Part Of The Result

The tab is read visually, at a glance, by someone scanning for a comparison.
Layout and color carry meaning, so they are part of the deliverable, not
decoration to skip.

- **Match the local conventions of the block you are writing into.** Read the
  neighboring rows' formatting before adding to them; a row that looks different
  reads as if it means something different.
- **Color is a signal with a defined meaning — do not invent one.** Where a tab
  assigns semantics to a color (a below-trivial score, an invalid protocol, a
  misconfiguration), apply it only under that exact condition, and never
  repurpose the same color for an unrelated note. A color applied loosely
  destroys the signal for every row that used it correctly. Project-specific
  color semantics live with the project — see `../projects/vlm_metrics.md`.
- **Inserting a row inherits the neighbor's formatting**, including backgrounds
  that encoded a condition your run does not meet. Clear inherited formatting,
  then apply only what you intend.
- **Keep the metric columns visible.** Long text in an early column, an
  unwrapped cell, or a stray merge pushes the numbers out of view and defeats
  the side-by-side comparison the layout exists to provide.
- **Read back what you wrote — values, formulas, and colors** — and, when the
  change is structural, look at the rendered tab rather than only the cell
  values. The `gsheets` CLI can export a page as an image for exactly this.

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
2. Resolve the tab by title and rebuild the column map from the live header.
3. Choose the row by §Where The Row Goes — find the baseline block this run
   varies and insert into it. Never append at the end by default.
4. Pull identity, config, final metrics, and step/loss continuity from the
   tracker and logs. Do not scan benchmark datasets merely to fill a diagnostic.
5. Normalize only metrics whose semantics are known, then run the comparability
   hard stop above.
6. Write the smallest range. Keep the text terse, fill `logdir` / `stagedir`,
   clear inherited formatting, and apply only the formatting you intend.
7. Read back values, formulas, and colors; render the tab when the change was
   structural.
8. Report the changed row, run id/name, missing diagnostics, and any caveat.

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
- **Whether it was produced by the protocol you are claiming.** Settle this from
  the protocol and the population, never from which job emitted the number. An
  in-training periodic evaluation IS reportable when it runs the protocol being
  claimed over a comparable population — that is a configuration choice, and
  where a project has made it, the training run's own curve is the result. Where
  it has not, the periodic evaluation runs at whatever depth, breadth, and
  sample count is cheap, and promoting it silently swaps the protocol underneath
  the claim. Read the config for the sample count and the protocol knobs; a
  number is not more trustworthy for having come from a dedicated job, nor less
  for having come from a training loop.
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
