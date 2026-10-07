---
name: charlm-runs
description: Launch, verify, harvest, and log char-LM torch-rnn reproduction runs on the GPU boxes, where one cell is one W&B group of seeds and one spreadsheet row.
---

# char-LM Runs — Running Research Against This Line

This skill relies on [the char-LM knowledge page](../../../knowledge/codebases/charlm.md)
for the code and box paths, the measured configuration, the split, what each
metric means, and the findings so far. Which workbook and tab a result goes to
is [knowledge/environment/result-workbooks.md §Which Tab](../../../knowledge/environment/result-workbooks.md#which-tab).

## Use the venv python on the box

**On the box run `~/work/charlm/.venv/bin/python`** (a `--system-site-packages`
venv; wandb 0.29.0, matplotlib, pytest). The bare `python3` has NO wandb, and
started from `~/work/charlm` it imports the `./wandb` LOG directory as an empty
namespace package: `AttributeError: module 'wandb' has no attribute 'init'` is
that, not a broken install.

## The logging pipeline — one cell = one W&B group = 4 seeds = one row

Every piece of that sentence is load-bearing; do not improvise a variant.

1. **Group routing lives in the launcher's `--wandb_group`, never in memory.** A
   run launched without an explicit group inherits whatever the predecessor
   hardcoded and lands in someone else's group.
2. **Stagger seed launches by ≥ 40 s.** Concurrent `wandb.init` handshakes time
   out and kill seeds silently, while the card still reads busy.
3. **Verify a launch by counting processes per seed**, matching on
   `/proc/*/cmdline` — never by the launcher's own `LAUNCHED` line, and never
   with `pgrep -f` through an `ssh --command` layer (quote mangling returns an
   empty list that reads as success).
4. **Harvest by GROUP, never by scanning a run list.** `api.runs(project)`
   returns only a recent window, so a scan reports 0 for a group that exists.
   `~/work/charlm/harvest.py` harvests by group and prints mean ± sd per column.
5. **train loss is a TAIL-WINDOW MEAN** over the last 10 logged points (quote the
   step window), never the single last sample. **The column is NATS, copied
   verbatim from `harvest.py`'s `train loss (tail-mean)` line.** `train/bpc` is
   already bits, so dividing it by ln 2 again is a double conversion — the bug
   that once put a grid on the tab at 2.08x its true value. Cross-check any new
   train-loss cell against a finished neighbour: a value above the val loss is a
   unit error, not a training run that underfits.

## Reading the verdict off the tab

**Judge a run by its train loss and val loss relative to neighbouring rows** —
there is no absolute target
([knowledge/codebases/charlm.md §The measured configuration](../../../knowledge/codebases/charlm.md#the-measured-configuration)). A run's headline is `val bpc (best
ckpt)`; keep the `(final)` columns beside it as the selection-free comparison.

## The row format

Columns, in order: `config / run · seed n · train loss (tail-mean) · val loss
(best ckpt) · val bpc (best ckpt) · val acc (best ckpt) · val loss (final) · val
acc (final) · wandb group · notes`. Every metric column is **`mean +- sd` over
the 4 seeds**; a bare number is a bug. Shared protocol goes in the **block header
row, once**; per-row notes carry only what changes interpretation. The
spreadsheet-write mechanics (the `gsheets --` trap, comma escaping, resolve-by-
title, read-back) are generic and owned by [result-logging skill](../result-logging/SKILL.md).

## Logging detail

Use `--logging_detail compact` by default; `full` enables the legacy
prediction / hidden / spectral / site diagnostics. Diagnostic failures must be
visible without aborting training, and historical W&B records must never be
mutated to resemble the current schema. `charlm/README.md` owns the exact keys
and clipping semantics.
