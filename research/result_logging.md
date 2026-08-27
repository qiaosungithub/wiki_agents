# Spreadsheet Result Logging

Owns writing a result into a project's shared experiment spreadsheet, and
finding the chart for a job. Per-tab column semantics belong to
`../projects/vlm_metrics.md` and `../projects/eqr_jax.md`; "a number is
meaningless without its protocol" belongs to `../engineering.md` §Communicating
A Result. **Read this every time you log**: a wrong row or column looks exactly
like a right one, and nothing errors. Write through the `gsheets` CLI
(`/google/bin/releases/gemini-agents-gsheets/gsheets`) and its skill, never by
scraping the URL.

## The Transaction

1. Resolve the input to an exact run, and where relevant an exact job attempt.
2. Resolve the tab **by title**; rebuild the column map from the live header.
3. Choose the row (§Where The Row Goes). Never append by default.
4. Pull identity, config, final metrics, and step/loss continuity from tracker
   and logs; never scan benchmark datasets to fill a diagnostic.
5. Normalize only metrics whose semantics are known, then run the hard stop
   (§Stop If It Is Not Comparable).
6. Write the smallest range: terse text, `logdir` / `stagedir` filled, inherited
   formatting cleared.
7. Read values, formulas, and colors back; render if the change was structural.
8. Report the changed row, run id, missing diagnostics, and any caveat.

**Only a run that reaches a conclusion is logged**; one that exposed a code bug
or a packaging failure belongs in the commit message. **Preemption is not such a
failure**: a job preempted but still reaching its step budget produced a real
result, and its final metrics — train loss included — must be harvested and
logged, never waved off as "see chart (log rotated)". The rotation is a place to
look harder (§Every Row Carries Its Train Metrics), not a licence to leave
columns blank. **Every row carries the chart link plus the `logdir` / `stagedir`
pointers**: they recover the exact code, command, and resolved config, which
lets the cells stay short; a row without a chart makes every reader rebuild the
URL by hand (§Chart Links).

## Which Tab

| Project | Spreadsheet | Tab |
|---|---|---|
| VLM (PaliGemma / JAX LLaVA) | `1FlcygQbGBTqHLJeiKdwxS0nP41SPMJrtX-kCJq8d7SQ` | the cleaned PaliGemma/JAX LLaVA tab |
| `EqR` / `EqR-jax` | `17pvrMbOKOKFiIa-eorO8Od12qc5JmrFCSXcXKeoe_u0` | **`EqR-refactored`** — `EqR-reproduction` is pre-refactor, read-only history |

**Resolve a tab by title, never by gid.** Both workbooks hold a tab with the
same gid for different projects, plus dated backup tabs of each other; a gid
writes your result into a frozen snapshot nobody reads. **A new line of work
opens a titled BLOCK at the bottom of the live tab by default**, as every family
there already does — not a new tab.

**The two EqR tabs disagree on columns I and J, in the direction that hurts**:
per-token and whole-board TRADE PLACES, so a row appended to `EqR-reproduction`,
or copied between tabs without re-deriving the map, silently swaps a 99.2 with a
34.8.

| Tab | I | J | columns the other lacks |
|---|---|---|---|
| `EqR-refactored` | `final train/token_acc` (per-token) | `final train/acc` (whole-board exact) | S `final train/total_loss`, T `in-train eval: acc / token-acc @ step` |
| `EqR-reproduction` | `accuracy` (per-token) | `exact_accuracy` (whole-board) | — |

## Re-Read The Header Every Time

**Never write from a remembered column map.** A stale map does not error when
someone adds a column, renames a metric, or reorganizes a tab — it files your
number under the wrong benchmark. Build the map from the live header,
**expecting the header not to be row 1** (these tabs open with a banner row and
often a reference row of trivial scores), and read the neighborhood before
choosing a range. **A helper script must re-derive the map on every run**: code
and spreadsheet drift independently, so a helper is never a source of truth.

## Where The Row Goes

**Decide the row before the values.** The tab is a set of ablation groups, not a
log; a reader navigates by adjacency, so appending at the end destroys the
comparison that makes the number mean anything.

| Case | Rule |
|---|---|
| Opening a family | A **full baseline row** carrying the configuration fixed beneath it, a free-text line naming the family, a blank row between families. |
| One axis changed | A variant row **directly beneath its baseline**, stating only what changed, written `- <change>` (`- only 128 tokens`); the leading `- ` is what marks a delta. |
| Filling a delta | **Leave inherited columns empty** — restating the baseline buries the one thing the row is about. A delta is relative to the **block's baseline**, not the row above; say so in the text when a change stacks on another variant. |
| Placing it | **Keep an ablation axis contiguous**: insert beside the comparison target. A change big enough to break the comparison starts a **new baseline block**, not a delta. |
| A published number | **A reference and a run of ours are different rows.** Give each dataset an `official baseline` row; restating its numbers inside a run's cells guarantees the two copies eventually disagree. |
| A train run and its eval | **Two rows, paired**, the eval directly beneath and titled `  ↳ eval of the row above`. They have different job ids, configs, and failure modes, so collapsing them loses which half went wrong. A train row with no eval row is a run without a conclusion: mark it, and never quote its in-training numbers as results. |
| A run past the block's budget | **Two rows, same job id**, because metric columns mean something only if every row stopped at the same step. Put the value **at the block's budget** in the run's own row and pair the longer result beneath as `  ↳ @<steps>, same run`, `Details` naming each segment. Still rising at the budget: that point is also its peak; otherwise record the pre-budget peak. **Never widen the tab with a second set of metric columns** — they stay empty for every normal-budget row, and an empty column reads as a missing measurement, not an inapplicable one. |

## Short Cells; Formatting Is Part Of The Result

**Do not write essays in a spreadsheet.** A cell helps the next reader find and
interpret the number, never explains how the run got that way. The test: *does a
reader need this sentence to USE the number?* If it only explains history it
belongs in the commit message or the project guide, and **a bug is never
explained in a cell**. The tab is read at a glance, so **a row that looks
different reads as if it means something different** — match the conventions of
the block you write into.

| Rule | Detail |
|---|---|
| **Settings stay short** | A whole baseline configuration fits in roughly 15–75 characters. |
| **Notes carry only what changes interpretation** | Protocol, sample count, what differs from the comparison row, any caveat on trusting the number — one clause each. |
| **Shared context goes in the block's header row, once** | Repeating a protocol per row is how these tabs decay: cells here reached 1,900 characters with one paragraph copied across seven rows. |
| **Color is a defined signal; never invent or repurpose one** | Applying one loosely destroys it for every row that used it correctly. Project semantics, and the full table of which colour is already taken: `../projects/vlm_metrics.md`. Check that table before applying a colour; a colour that looks free usually is not. |
| **Clear inherited formatting, then apply intentionally** | Inserting a row copies the neighbor's, including backgrounds encoding a condition your run does not meet. |
| **The CLI splits cell text on `,` and `|`** | A comma starts a new COLUMN and a pipe a new ROW, so an unescaped prose note scatters across the metric columns and the row below, overwriting real data that reads back as plausible. Escape commas (`\,`), keep pipes out of the text, and read the whole written range back. |
| **Keep the metric columns visible** | Long text in an early column defeats the side-by-side comparison the layout exists for. |
| **Read colors back, not just values** | Render the tab (export PNG) after a structural change. |

## Every Row Carries Its Train Metrics

**A results row is incomplete until its train-metric columns are filled, and
train loss is never optional.** The eval number is the headline, but the train
columns (`final train/lm_loss`, `final train/token_acc`, `final train/acc`) show
*why* an arm sits where it does — an arm that never fit and one that fit but
failed to generalize read identically in eval and oppositely in train loss. A
row with eval filled and train columns blank discards half of every lr×wd
comparison the tab exists for.

- **Harvest the train metrics as part of the transaction, not as a nice-to-have.**
  Step 4 ("pull final metrics from logs") includes them; do not treat them as a
  separate errand you skip when the log is awkward.
- **"The log rotated" is a lookup problem, not an exemption.** The framework
  prints per-step train metrics from exactly one worker, and after a preemption
  that worker is a *different* physical log file. Find it before writing "see
  chart". Which `rank_<n>.log` holds the final train curve:
  `../projects/eqr_jax.md` §Harvesting Final Train Metrics.
- **Report a train metric as a tail-window mean over the logged curve**, not the
  single last row (§Stop If It Is Not Comparable, "Converged value or single
  sample"; `../projects/eqr_jax.md` §Divisors and cadence).
- **Match the block's format for each column** — these tabs are inconsistent
  (`token_acc` is a percent in one section and a fraction in another), and a
  number in the wrong convention reads as a 100x error. Read the neighbors, not
  your memory. On `maze64-clean`, the accuracy columns (ss20 / ss100
  `solution_acc`, D/E) are kept on a **0-100 scale** (`0.924` → `92.4`, a genuine
  `0` stays `0`); convert any fraction-scale value before writing, and normalize
  a mixed column to 0-100 in one pass. A sub-1% accuracy (e.g. `0.3` meaning
  0.3%) is a legitimate 0-100 value — disambiguate by the arm, not the magnitude.
- **Unrecoverable is the rare exception, and it is stated, not left blank.** If
  the metric truly cannot be recovered, write why in one clause (`train log lost
  to N preemptions`) so a blank never reads as an unlogged oversight — but
  exhaust the lookup first.

## Stop If It Is Not Comparable

**Do not write when the run and the sheet are not directly comparable**: a
metric is missing or renamed, the split or protocol differs, final evaluations
disagree, training continuity is unexplained, target cells conflict, or the task
would need cross-region access. Report the discrepancy instead; the user decides
how to represent an out-of-distribution result. **For bulk reformatting or
structural cleanup, duplicate the worksheet first** unless the user authorizes
changing the original.

The recurring failure is two numbers that look alike and mean different things —
`../engineering.md` §Communicating A Result owns the general rule; five things
decide whether a specific value may enter a row:

| Settle | Because |
|---|---|
| The population | An eval padded to a fixed batch shape reports over padded rows, and padding can score as correct, inflating derived figures while one unaffected metric quietly disagrees. Establish the real denominator, correct explicitly, say so in the notes. |
| Converged value or single sample | A "final" training metric is usually the one step that landed on the logging grid, carrying full batch-to-batch variance. Record a tail-window mean with its step range and compare on that. |
| The protocol behind it | An in-training periodic eval runs at whatever is cheap: a health signal, not a headline. The paired eval row is the result. |
| Whether the run finished | Just short of budget may be a log-point boundary; well short is an interruption. Record steps completed — an eval of a short checkpoint is pessimistic and the row must admit it. |
| Which variant of a benchmark | Averaging convention, answer extraction, split, and scoring mode each change the number under one benchmark name, and each has its own trivial-score floor. |

Two checks settle a disputed correction: it must agree exactly with an
independent metric of the same thing, and multiplying by the population must
give a whole count. Project semantics: `../projects/eqr_jax.md`,
`../projects/vlm_metrics.md`.

## Chart Links

A cluster job has no external tracker run, so "the chart" is a different URL per
backend. Resolve the one the job actually wrote — a URL that renders an empty
page is worse than no link.

| Link | Shows |
|---|---|
| `http://flatboard/xid/<XID>` | the metric **curves** — this is the link to log |
| `http://datatable/xid/<XID>/data` | the raw scalar table behind them |
| `http://xids/<XID>` | the experiment page (status, work units, config) |

**An empty page means no data was written, not a broken link.** The writer
announces itself on rank 0 at startup; a "could not start" or "log-only" warning
means the curves do not exist. **Opting in to the table writer must be
explicit** — the default writes nothing, with no error. A short `eval_only` job
may never reach the flush threshold, so its durable evidence is the metrics
files under the checkpoint bucket: log that path too. Wiring:
`../projects/eqr_jax.md` §Experiment Tracking.

**Writing a datatable requires a Borg credential; a workstation cannot.** The
table lives at `owner=…deepmind-jobs realm=… type=PROD`, and a workstation LOAS
is a *restricted* credential — `DatatableService.CreateTable` / `Read` both
return `PERMISSION_DENIED` (`go/loas-restricted-credentials`), as do `analog`
and `xmanager tail_logs`. So a metric only reaches a table from inside a work
unit, which mints a real prod credential; `blaze run` on the workstation fails
at table creation, and cannot verify the write either — read the job's own CNS
log (the writer prints `writing to http://flatboard/xid/<XID>`), or have the job
drop a small CNS completion marker a watcher can poll.

**A finished run's empty chart can be backfilled from its text log.** A run that
completed before the code had a datatable writer still has every logged scalar
in its `_boot_log` stream on CNS. A tiny CPU replay job (parse the rank-0 log,
re-emit via the same writer, keyed by the *new* job's XID) reconstructs the
curves; the source XID's table cannot be written after its work unit ends, so
the row points at the replay XID. Run it as a **g9 PROD CPU controller**
(`--tpu_type=cpu=N --group=9 --tier=PROD --skip-preflight --cell=<in-metro>`):
the g8 shared CPU pool routinely sits unscheduled (experiment `RUNNING`, work
unit never executes — no heartbeat, no log), while the PROD controller schedules
in ~1 min (§the CPU-only bullet in `../jobs.md`).

### Provenance: what the chart link does not carry

**A chart link resolves to metrics only.** It cannot say which code produced
them, so a row carrying only a chart link cannot answer "which snapshot was
this?" — the question a reproduction table exists for. The launcher writes these
into the job registry (`~/.tpu_jobs.json`, keyed by job id); none reaches the
chart or the experiment page:

| Field | Why the chart cannot recover it |
|---|---|
| `stagedir` | The immutable source snapshot that was packaged. The home checkout has moved on; this is the only pointer to the exact code. |
| `logdir` | The launch log: command, resolved flags, allocator verdict. |
| eval outputs | Per-point metrics files and the FULLY RESOLVED eval config, including arch merged from the checkpoint. Survives when the table service has nothing. |

```bash
python3 -c "import json; e=json.load(open('$HOME/.tpu_jobs.json'))['<XID>'];
print(e['stagedir'], e['logdir'], e['bucket_cp_path'], sep='\n')"
```

`tpu clear` archives rather than deletes, so an old id still resolves from the
legacy file — but that registry is a local file on one workstation: the second
reason to copy these fields into the sheet.
