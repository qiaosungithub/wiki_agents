# Spreadsheet Result Logging

Frequent, and the easiest place to silently corrupt the record: a wrong column
or a wrong row looks exactly like a right one. Read this before every write.

Use the `gsheets` CLI (`/google/bin/releases/gemini-agents-gsheets/gsheets`);
never scrape the URL. See the `gsheets` skill.

| Project | Spreadsheet | Tab |
|---|---|---|
| VLM (PaliGemma / JAX LLaVA) | `1FlcygQbGBTqHLJeiKdwxS0nP41SPMJrtX-kCJq8d7SQ` | the cleaned PaliGemma/JAX LLaVA tab |
| `EqR` / `EqR-jax` | `17pvrMbOKOKFiIa-eorO8Od12qc5JmrFCSXcXKeoe_u0` | **`EqR-refactored`** — every new run. `EqR-reproduction` is the OLD tab, read-only history |

**New EqR runs go to `EqR-refactored`, never to `EqR-reproduction`.** The latter
predates the refactor and is kept for history; a result appended there is filed
under a build whose metrics have different names. Do not create a per-topic tab
either — a new line of work opens a titled BLOCK at the bottom of
`EqR-refactored`, the way every family already there does.

**The two tabs disagree on columns I and J, in the direction that hurts.**
`EqR-refactored` is `I = final train/token_acc`, `J = final train/acc`
(whole-board exact); `EqR-reproduction` is `I = accuracy`, `J = exact_accuracy`
— i.e. the per-token and whole-board numbers TRADE PLACES between the two. The
refactored build also renamed the metrics themselves: `acc` is now whole-board
exact and `token_acc` is per-token. Copying a row from one tab to the other
without re-deriving the column map silently swaps a 99.2 with a 34.8. It also
carries two columns the old tab lacks (S `final train/total_loss`, T `in-train
eval: acc / token-acc @ step`).

**Fill the chart column.** `http://flatboard/xid/<xid>` for anything that
reached the metric sink; a row with an xm link and no chart makes every reader
reconstruct the same URL by hand.

**Resolve a tab by title, never by gid.** Both workbooks contain a tab with the
same gid holding different projects, plus dated backup tabs of each other —
landing in one writes your result into a frozen snapshot nobody reads.

## What Gets Logged

Only a run that reaches a **conclusion**. A run that exposed a code bug, a
packaging failure, or a preemption belongs in the commit message, not here.

Every row needs the chart link **and the `logdir` / `stagedir` pointers**. The
pointers matter more than any prose: they recover the exact code, command, and
resolved config, which is what lets the text stay short. See §Provenance.

## Re-Read The Header Every Time

**Never write from a remembered column map.** Someone adds a benchmark column,
renames a metric, or reorganizes a tab between sessions. A stale map does not
error — it files your number under the wrong benchmark.

Each time: resolve the tab by title → build the column map from the live header
→ read the neighborhood you are writing into → write the smallest range → read
it back. Expect the header not to be row 1; these tabs open with a banner row
and often a reference row of trivial scores.

**Helper scripts are worth keeping but must re-derive the column map on every
run.** Code and spreadsheet drift independently, and either can change without
the other. A helper is a convenience, never a source of truth.

## Where The Row Goes

**Decide the row before the values.** The tab is a set of ablation groups, not a
log; a reader navigates it by adjacency, so appending at the end destroys the
comparison that makes the number mean anything.

- A group opens with a **full baseline row** carrying the configuration that
  stays fixed beneath it. A free-text line names the family; a blank row
  separates families.
- **Variants sit directly beneath their baseline and state only what changed**,
  written `- <change>` (`- only 128 tokens`, `- fix randomness`). The leading
  `- ` is what marks a delta.
- **A delta leaves inherited columns empty** and never restates the baseline's
  setting. Re-describing fixed axes buries the one thing the row is about.
- **A delta is relative to the block's baseline**, not the row above it. Say so
  in the text when a change stacks on another variant.
- **Keep an ablation axis contiguous** — insert next to the comparison target.
- A change large enough to break the comparison starts a **new baseline block**,
  not a delta row.

**A reference number and a run of ours are different rows.** Give each dataset
an `official baseline` row; never restate its numbers inside a run's cells, or
the two copies will eventually disagree.

**A train run and its eval are different rows, paired.** The eval row sits
directly beneath, titled `  ↳ eval of the row above`. They have different job
ids, configs, and failure modes, so collapsing them loses the ability to say
which half went wrong. A train row with no eval row is a run without a
conclusion — mark it, do not quote its in-training numbers as results.

**A run that outlasts its block's budget is logged as two rows, not one.** The
metric columns of a block are only meaningful if every row in them stopped at
the same step. So put the value **at the block's budget** in the metric columns
of the run's own row, and pair the longer result directly beneath as
`  ↳ @<steps>, same run` — same shape as the train/eval pair above. Both rows
carry the same job id; the `Details` cell names which segment each one covers.
If the run is still rising at the block's budget, the shorter point is also its
peak and there is nothing to choose; otherwise record the pre-budget peak, since
a single endpoint on the logging grid is not the run's best behaviour.

Do not instead widen the tab with a second set of metric columns. Those columns
stay empty for every row that ran the normal budget, which is most of them, and
an empty column is read as a missing measurement rather than an inapplicable
one. Adding a row costs nothing and keeps the comparison vertical.

## Write Short Cells

**Do not write essays in a spreadsheet.** A cell exists to let the next reader
find and interpret the number, not to explain how the run got that way. The
test: *does a reader need this sentence to USE the number?* If it only explains
history, it belongs in the commit message or the project guide.

- **Settings stay short** — a whole baseline configuration fits in roughly
  15–75 characters.
- **Notes carry only what changes interpretation**: the protocol, the sample
  count, what differs from the comparison row, and any caveat affecting how much
  to trust the number. Usually one clause each.
- **Shared context goes in the block's header row, once.** When several rows
  share a protocol or a recipe, state it above them; repeating it per row is how
  these tabs decay. Cells here reached 1,900 characters with the same paragraph
  copied verbatim across seven rows.
- **Never explain a bug in a cell.**

## Formatting Is Part Of The Result

The tab is read visually, at a glance, by someone scanning for a comparison.

- **Match the conventions of the block you write into**; a row that looks
  different reads as if it means something different.
- **Color is a defined signal — do not invent or repurpose one.** Applying a
  color loosely destroys it for every row that used it correctly. Project
  semantics: `../projects/vlm_metrics.md`.
- **Inserting a row inherits the neighbor's formatting**, including backgrounds
  encoding a condition your run does not meet. Clear, then apply intentionally.
- **Keep the metric columns visible.** Long text in an early column defeats the
  side-by-side comparison the layout exists for.
- **Read back values, formulas, and colors**; render the tab (export PNG) after
  a structural change.

## Stop If It Is Not Comparable

Do not write when the run and the sheet are not directly comparable: a metric is
missing or renamed, the split or protocol differs, final evaluations disagree,
training continuity is unexplained, target cells conflict, or the task would
need cross-region access. Report the discrepancy instead — the user decides how
to represent an out-of-distribution result. An agent must not silently force it
into the schema.

For bulk reformatting or structural cleanup, duplicate the worksheet first
unless the user explicitly authorizes changing the original.

## A Metric Is Not Comparable Until Its Protocol Is

The recurring failure is two numbers that look alike and mean different things.
Before writing any value, settle:

- **The population.** An evaluation padded to a fixed batch shape reports over
  padded rows, and padding can score as correct — inflating derived figures
  while one unaffected metric quietly disagrees. Establish the real denominator,
  correct explicitly, and say so in the notes.
- **Converged value or single sample.** A "final" training metric is usually the
  one step that landed on the logging grid, carrying full batch-to-batch
  variance. Record a tail-window mean with its step range and compare on that.
- **The protocol that produced it.** An in-training periodic eval runs at
  whatever is cheap; it is a health signal, not a headline. The paired eval row
  is the result.
- **Whether the run finished.** Stopping just short of budget may be a log-point
  boundary; stopping well short is an interruption. Record steps completed —
  an eval of a short checkpoint is pessimistic and the row must admit it.
- **Which variant of a benchmark.** Averaging convention, answer extraction,
  split, and scoring mode all change the number under one benchmark name, and
  each has its own trivial-score floor.

Two checks settle a disputed correction: it should agree exactly with an
independent metric measuring the same thing, and multiplying by the population
should give a whole count.

Project-specific semantics: `../projects/eqr_jax.md`, `../projects/vlm_metrics.md`.

## Transaction

1. Resolve the input to an exact run and, when relevant, an exact job attempt.
2. Resolve the tab by title; rebuild the column map from the live header.
3. Choose the row per §Where The Row Goes. Never append by default.
4. Pull identity, config, final metrics, and step/loss continuity from the
   tracker and logs. Do not scan benchmark datasets to fill a diagnostic.
5. Normalize only metrics whose semantics are known, then run the hard stop.
6. Write the smallest range: terse text, `logdir` / `stagedir` filled, inherited
   formatting cleared.
7. Read back values, formulas, and colors; render if the change was structural.
8. Report the changed row, run id, missing diagnostics, and any caveat.

## Chart Links

A cluster job has no external tracker run, so "the chart" is a different URL per
backend. Resolve which one the job actually wrote; a URL rendering an empty page
is worse than no link.

| Link | Shows |
|---|---|
| `http://flatboard/xid/<XID>` | the metric **curves** — this is the link to log |
| `http://datatable/xid/<XID>/data` | the raw scalar table behind them |
| `http://xids/<XID>` | the experiment page (status, work units, config) |

**An empty page means no data was written, not a broken link.** Verify before
trusting one: the writer announces itself on rank 0 at startup, and a
"could not start" or "log-only" warning means the curves do not exist. Opting in
to the table writer must be explicit — the default silently writes nothing, with
no error. A short `eval_only` job may never reach the flush threshold; its
durable evidence is the metrics files under the checkpoint bucket, so log that
path too. Project wiring: `../projects/eqr_jax.md` §Experiment Tracking.

## Provenance: What The Chart Link Does Not Carry

A chart link resolves to **metrics only**. It does not identify the code that
produced them, so a row carrying only a chart link cannot answer "which snapshot
was this?" — exactly the question a reproduction table exists to answer.

The launcher writes these into the job registry (`~/.tpu_jobs.json`, keyed by
job id); they never reach the chart or the experiment page:

| Field | Why the chart cannot recover it |
|---|---|
| `stagedir` | The immutable source snapshot that was packaged. The home checkout has moved on; this is the only pointer to the exact code. |
| `logdir` | Holds the launch log: the command, resolved flags, and allocator verdict. |
| eval outputs | Per-point metrics files and the FULLY RESOLVED eval config, including arch merged from the checkpoint. Survives when the table service has nothing. |

```bash
python3 -c "import json; e=json.load(open('$HOME/.tpu_jobs.json'))['<XID>'];
print(e['stagedir']); print(e['logdir']); print(e['bucket_cp_path'])"
```

`tpu clear` archives rather than deletes, so an old id still resolves from the
legacy file — but it is a local file on one workstation, which is a second
reason to copy these fields into the sheet.
