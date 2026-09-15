# Spreadsheet Result Logging

Owns writing a result into the shared VLM experiment spreadsheet. Which number
each benchmark name means, its trivial floor, and what each background colour
means are `vlm_metrics.md`; the experiment loop is `research.md`. Read this page
every time you log, because a wrong row or column looks like a right one and
nothing errors.

Chapter 1 is the transaction; Chapter 2 is where the row goes and what a cell
holds; Chapter 3 is the writes and readings that go wrong.

---

## Chapter 1 — The Transaction

### The default target

**Log into the cleaned PaliGemma/JAX LLaVA tab in spreadsheet
`1FlcygQbGBTqHLJeiKdwxS0nP41SPMJrtX-kCJq8d7SQ`, resolved by title rather than
gid, and inspect the live workbook before trusting a saved tab name or row
number.**

- The workbook also holds dated backup tabs, so a stale gid or name can write into a frozen snapshot nobody reads.
- A new line of work opens a titled block at the bottom of the live tab, not a new tab.

### Re-read the header every time

**Never write from a remembered column map, because a stale map files a number
under the wrong benchmark without an error.** Build the map from the live header,
and do not assume the header is row 1: a tab can open with a banner row and a
reference row of trivial scores. A helper must re-derive the map on every run; it
is never a source of truth.

### The transaction

**Every logging request runs these steps in order.**

1. Resolve the input to an exact WandB run and, when relevant, an exact infra job attempt. An 8-character id is normally unified infra; a 4-digit id may be a legacy tmux window.
2. Resolve the tab by title and build the column map from the live header.
3. Choose the row (Chapter 2) before any value, and do not append at the end by default.
4. Pull identity, config, final metrics including train accuracy and loss, and step/loss continuity from WandB and logs. Do not scan benchmark datasets merely to fill a diagnostic.
5. Normalize only metrics whose semantics are known (`vlm_metrics.md`), then run §Stop if it is not comparable.
6. Write the smallest range, preserve the WandB link, clear inherited formatting, and apply only intentional formatting.
7. Read back values, formulas, and colours, and render the tab after a structural change.
8. Report the changed row, run id/name, missing diagnostics, and any caveat.

### Stop if it is not comparable

**Do not write when the run and the sheet are not directly comparable.** Stop and
report the discrepancy if a metric is missing or renamed, the split or protocol
differs, final evaluations disagree, training continuity is unexplained, the
target cells conflict, or the task would require cross-region benchmark or
checkpoint access. The user decides how to represent an out-of-distribution
result; never force it silently into the existing schema.

Two numbers that look alike can mean different things, so settle these before a
value enters a row:

| Settle | Because |
|---|---|
| The population | An eval padded to a fixed batch shape reports over padded rows, and padding can score as correct, inflating derived figures while an unaffected metric disagrees. Establish the real denominator, correct explicitly, and note it |
| Converged value or single sample | A "final" training metric is often the one step that landed on the logging grid, with full batch-to-batch variance. Say which one you recorded |
| The protocol behind it | An in-training periodic eval is a health signal, not a headline; the final eval is the result |
| Whether the run finished | Just short of the budget may be a logging boundary; well short is an interruption. Record the steps completed, because an eval of a short checkpoint is pessimistic |
| Which variant of a benchmark | Averaging convention, answer extraction, split, and scoring mode each change the number under one benchmark name, and each variant has its own floor (`vlm_metrics.md`) |

- A disputed correction must agree exactly with an independent metric of the same thing, and multiplying it by the population must give a whole count.
- Duplicate the worksheet before bulk reformatting or structural cleanup, unless the user explicitly authorizes changing the original.
- Historical column maps, thresholds, and API snippets are in `archive/details/spreadsheet_logging_playbook.md`, for when the live sheet alone is insufficient.

---

## Chapter 2 — Where The Row Goes And What A Cell Holds

### Choose the row before the values

**Decide the row before the values, because readers compare rows by adjacency and
a row appended at the end compares with nothing.**

1. If the user named an exact row, use it after checking that the write will not overwrite conflicting data.
2. If an existing row already represents the run and its cells are blank, fill that row.
3. For an eval-only rerun of a known training row, update that row only when it is clearly the same experiment and the previous eval was wrong or incomplete.
4. For a pretrain/SFT pair, use two adjacent rows, stage-1 final metrics first and stage-2 final metrics second, even when one WandB run covers both stages.
5. Place a JAX LLaVA reproduction run in the LLaVA reproduction block, near rows with the same architecture and ablation key. Keep prompt-causal rows together, late-fusion rows by `txt_feature_layer`, and scale, connector, freeze, or LM ablations beside the row they differ from.
6. Place a PaliGemma recipe ablation near rows of the same recipe family that differ only in the intended key.

If the new run differs from nearby rows in more than the expected key, say so and
stop before writing, unless the user already acknowledged the difference.

### The tab is a set of ablation groups

**Keep each ablation axis contiguous: a variant sits directly under the baseline
it changes, and a change big enough to break the comparison starts a new baseline
block.**

- Write a variant's setting as a delta, `- <change>`, and leave inherited columns empty rather than restating the baseline.
- A published number gets its own `official baseline` row, never a copy inside a run's cells.

### Short cells

**A cell helps the next reader find and interpret the number, never how the run
got that way.** Match the block you write into, because a row that looks different
reads as meaning something different.

| Rule | Detail |
|---|---|
| Settings stay short | A whole baseline configuration fits in a short label |
| Notes carry only what changes interpretation | Protocol, sample count, what differs from the comparison row, or a caveat on trusting the number, one clause each |
| Shared context goes in the block header row, once | Repeating a protocol on every row is how cells grow into paragraphs |
| Colour is a defined signal | Never invent or repurpose a colour; `vlm_metrics.md` owns which colours are taken |
| Clear inherited formatting, then apply it intentionally | An inserted row copies its neighbour's backgrounds, which encode a condition your run may not meet |
| Keep the metric columns visible | Long text in an early column defeats the side-by-side comparison |
| One fact, one column; one unit per column | An id that has a home in another column does not belong in the note too, and a column mixing fractions with percents cannot be sorted, so state the unit in the header |

### Note (B) style

**Keep a Note (B) cell verdict-first and under about 300 characters, or about 600
for a row with a special finding, because long notes do not get read.**

1. The single-axis diff against the parent (config key and values), and the job id or run name.
2. The verdict with its Z delta against the parent row, such as `Z 34.08 → −0.96 net negative`. Both `Z` values must use one definition (`vlm_metrics.md` §The composite score in Z).
3. The two or three sharpest metric deltas; the rest live in the metric columns.
4. Hard caveats that change interpretation, such as train columns `I`/`J` that are not comparable, the RefCOCOg valid-answer ratio, or a protocol mismatch.
5. Metrics that have no sheet column, as a compact tail: `W&B-only: DocVQA x.xx, RWQA yy.y`.

Write the eval protocol once on the family base row, not on every row, and do not
repeat numbers already in the columns except to quote a delta. Before condensing
existing notes, back up the originals under `work/sheet_backups/`.

---

## Chapter 3 — Writes And Readings That Go Wrong

### A filled row can still be wrong

**Before adding a rung under a summary row, re-derive the summary from the cells
it describes, because the head row is the one people quote and it goes stale when
a rung changes.** Mark the correction in the note rather than silently swapping
the number.

- Before overwriting a row that already holds numbers, re-harvest from WandB or the job's `dead_runs` attempt logs, because a relaunch overwrites the on-disk log of the attempt that finished.
- Mark a row harvested mid-run `NOT FINAL` in the note and put the step in the verdict cell, so it cannot be quoted as final later.
- Never put an agent, session, or batch tag in a results row. A tab records what was run, in the tab's own vocabulary, which you learn from the neighbouring block headers.

### Row numbers change under your own writes

**Inserting a row shifts every row below it, so any row index resolved before the
insert is stale, including the ones in the note you are about to write.**

- Cite a row by its content plus its row number, never by a bare row number, and re-read the neighbourhood after any structural write.
- Someone else may reorder the tab between your write and your read-back, so immediately before every write, read a bounded range `A<lo>:B<hi>` and match on the Settings text.

### A value that starts with a plus or equals sign becomes a formula

**Under `value_input_option="USER_ENTERED"`, which a write needs for
`=HYPERLINK(...)` links to work, a value starting with `+` or `=` is parsed as a
formula, and `+0.150 (live)` lands as `#ERROR!`.** Write signed numbers without
the leading plus, or lead with a word, and read the cell back.

### An inserted row inherits formatting

**`insert_rows(inherit_from_before=True)` copies the backgrounds of the row above,
so after inserting, clear `A:E` and `F:X` before reapplying any colour
(`vlm_metrics.md`).** A row inserted under a `[wrong config]` block otherwise
inherits its red `A:D` label cells.

### A colour check that cannot fail

**Before trusting a colour reading, read the unchanged sheet twice and compare the
two readings; a reader that reports changes there is measuring itself, not the
sheet.**

- Read colours through the API grid data (`fetch_sheet_metadata` with `includeGridData`), or parse an xlsx export with `openpyxl` and resolve each cell to its actual RGB. A hand-rolled XML or regex reader returns plausible wrong numbers.
- Style indices are not comparable across two exports of the same workbook, because the same styles come back in a different order.
- Recolour by explicit row range, such as a `repeatCell` request over `startRowIndex` and `endRowIndex`, never by editing a style that other rows share.
- Before a bulk recolour, keep a pre-change export as the rollback, and report the measured count of cells changed outside the target.
- When a colour gains a second meaning, rewrite its legend in `vlm_metrics.md` in the same edit.
