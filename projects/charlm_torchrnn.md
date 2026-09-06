# char-LM — torch-rnn reproduction (science line)

Character-level language modelling on tiny-shakespeare, reproducing
**`jcjohnson/torch-rnn`**. The purpose is a credible dense-supervision LM
setting in which to test this group's RNN mechanism work, whose home is the
adding problem (`rnn_unroll_adding.md`).

## The Setting Is Ambiguous Unless You Name The Repo

**"char-RNN" names at least five incompatible setups; say which one.** Their
numbers share the unit (nats/char) and are not comparable.

| Repo | What it is | Why it differs |
|---|---|---|
| **`jcjohnson/torch-rnn`** (ours) | Adam, learned embedding, 0.8/0.1/0.1 sequential split | the line below |
| `karpathy/char-rnn` | RMSprop 2e-3, one-hot, 0.95/0.05, no test split | different data AND optimiser |
| `karpathy/min-char-rnn.py` | 100-line numpy vanilla RNN | no batching, no val split |
| `salesforce/awd-lstm-lm` enwik8 | 3x1840 LSTM, 47M params, BPC 1.232 | a tuned recipe, 90M chars, 47 GPU-hours |
| nanoGPT `shakespeare_char` | Transformer | same vocab, nothing else shared |

## Where Everything Is

| Thing | Path |
|---|---|
| Code | `~/work/charlm/` (`data_prep.py`, `data_loader.py`, `model.py`, `metrics.py`, `train.py`, `test_data.py`; unroll: `unroll_model.py`, `unroll_optimizer.py`, `unroll_util.py`, `site_probe.py`, `test_unroll.py`) |
| Interpreter ON THE BOX | **`~/work/charlm/.venv/bin/python`** (a `--system-site-packages` venv; every cell on the tab ran under it, see `wandb-metadata.json` → `executable`). The bare `python3` has NO wandb and, started from `~/work/charlm`, imports the `./wandb` LOG directory as an empty namespace package: `AttributeError: module 'wandb' has no attribute 'init'` is that, not a broken install. |
| Launchers | `run_official.sh` (torch-rnn default), `lu_d0.sh` (2026-09-05 dropout-0 unroll lr sweep: 3 lr x 4 seeds, 3 per GPU, 45 s stagger, DONE-marker skip) |
| Upstream Lua mirror (read-only reference) | `~/work/torch-rnn-upstream/` |
| Native docs | `~/work/charlm/README.md` — measured config table, deliberate divergences |
| Launcher | `~/work/charlm/run_official.sh` (every flag spelled out, not inherited) |
| Compute | the 4xA100 boxes; SSH in `../gcp_gpu_ssh.md`. Since 2026-09-06 `~/work/charlm` + `.venv` (system-site-packages, wandb 0.29.0, matplotlib, pytest) + prepared data exist on ALL THREE of `qiaos-4a100-3` (80GB, the main one), `qiaos-4a100` and `qiaos-4a100-2` (40GB, 2 unroll runs per card); code is copied by tarball from the cloudtop copy, so the cloudtop copy is the source of truth and md5s must match before a launch |
| W&B | project `charlm-torchrnn-baseline`, entity zhh24-massachusetts-institute-of-technology |
| Results tab | EqR workbook `17pvrMbOKOKFiIa-eorO8Od12qc5JmrFCSXcXKeoe_u0`, tab **`charlm-torchrnn (qiaos)`** (resolve BY TITLE) |

## The Measured Configuration

Read out of upstream source, then recomputed locally. tiny-shakespeare is
1,115,394 chars, vocab 65, sha256 `86c4e6aa9db7c042…`.

| | value |
|---|---|
| split (0.8/0.1/0.1, **sequential**) | train 892,316 · sel 111,539 · val 111,539 |
| batches at B=50, T=50 | 356 / 44 / 44 |
| total steps at `max_epochs=50` | 17,800 (356/epoch) |
| parameters (lstm L2 h128) | 243,969 |
| uniform floor | 6.0224 bpc |
| **train-unigram floor** | **4.7742 bpc** |
| measured val bpc (official recipe, 4 seeds, best ckpt) | **2.5775 ± 0.0227 bpc** |
| measured val acc (same) | **0.4987 ± 0.0090** |
| cost | ~1 min/seed on one A100-80GB (3.0 ms/step, 78 MB) |

**Report against the unigram floor, not the uniform one.** A model that has
learnt only letter frequencies already reaches 4.7742 bpc.

## There Is No Official torch-rnn Validation Loss

**Do not go looking for a target number; the repo does not publish one.**
Checked README, `doc/flags.md` and the issue tracker: the only published
benchmark is **speed and memory over the first 100 iterations**. So the
baseline is what we measure, and it is comparable only to runs on this same
split. Also do not import an lr or a schedule from `awd-lstm-lm`: that one IS a
tuned recipe (paper Table 6) but for a different dataset and model scale.

## Splits, And What Selecting On val Costs

The byte boundaries are upstream's; the roles are ours.

| Slice | Role here | Upstream called it |
|---|---|---|
| first 80% | `train` | train |
| middle 10% | **unused** (kept so the boundaries stay identical; `--eval_sel` to measure it) | val |
| final 10% | **`val`** — never trained on; the online eval split | test (upstream never touches it) |

**The checkpoint is selected by the lowest online val loss — upstream's own
protocol — so `val` was never TRAINED on but WAS SELECTED on, and those are
different claims.** Picking the best of ~18 checkpoints buys an optimistic bias.
Since its size is not knowable in advance, both are logged and neither is
derived from the other:

| Key | Model | Meaning |
|---|---|---|
| **`val_best/*`** | selected checkpoint | **the protocol number, the headline** |
| `val_final/*` | model at the step budget | selection-free comparison |
| `val_best_minus_final_bpc` | — | the bias, measured per run |

**Never quote the headline without the bias term beside it.** Measured at this
budget: **-0.0022 ± 0.0021 bpc**, negligible because the lr decays to 1.95e-6 and
the model stops moving well before the end. That is a property of THIS schedule
and must be re-checked whenever it changes.

**Loss and accuracy do not peak at the same step, so a checkpoint chosen on loss
is not the accuracy-optimal one.** Seed 2 selected at step 2000 on val loss and
its val acc there is 0.4852, against 0.5039 for the final model — a 1.9-point
drop invisible in the loss column. This is the concrete reason `val acc (final)`
stays in the tab next to `val acc (best ckpt)`; a single accuracy column would
report whichever the loss happened to pick.

`data_prep.py` carries `schema_version = 2` and refuses a directory written
under the old `train/val/test` naming, where "val" was the middle slice:
loading it silently would put every number on the wrong bytes.

## Two Upstream Quirks Reproduced Deliberately, Both Behind Flags

* **`--adam_reset_on_decay 1`** (default): `train.lua` replaces the whole
  `optim_config` table on each decay, so **Adam's m/v are discarded every 5
  epochs**. `0` decays in place and keeps the moments.
* **`--grad_clip_mode clamp`** (default): element-wise clamp to ±5, **not** a
  norm clip. `norm` is what most modern code means by "grad_clip 5".

The default schedule takes lr from 2e-3 to **1.95e-6 by epoch 50 (÷1024)**. For
arm comparisons calibrated on `u_norm`, use a constant lr
(`--lr_decay_factor 1.0`) and treat decay as its own variable.

## Known, Explained Divergences From Upstream

| Thing | Upstream | Here | Why |
|---|---|---|---|
| parameters | 242,945 | 243,969 | PyTorch `nn.LSTM` carries both `bias_ih` and `bias_hh` (+4H/layer). Arithmetic only. |
| token ids | 1-indexed (Lua) | 0-indexed | bijection; loss identical, checkpoints NOT interchangeable |
| gate order | (i,f,o,g) | PyTorch (i,f,g,o) | only affects the forget-bias fill, written to the f-slice **by meaning** |

## The Logging Pipeline (follow it; do not improvise a variant)

**One cell = one W&B group = 4 seeds = one spreadsheet row.** Every piece of
that sentence is load-bearing.

1. **Group routing lives in the launcher**, never in memory. A run launched
   without an explicit `--wandb_group` inherits whatever the predecessor
   hardcoded and lands in someone else's group.
2. **Stagger seed launches by >= 40 s.** Concurrent `wandb.init` handshakes time
   out and kill seeds silently, while the card still reads busy.
3. **Verify a launch by counting processes per seed**, matching on
   `/proc/*/cmdline` — never by the launcher's own `LAUNCHED` line, and never
   with `pgrep -f` through an `ssh --command` layer (quote mangling returns an
   empty list that reads as success).
4. **Harvest by GROUP, never by scanning a run list.** `api.runs(project)`
   returns only a recent window, so a scan reports 0 for a group that exists.
   `~/work/charlm/harvest.py` does this and prints mean ± sd per column.
5. **train loss is a TAIL-WINDOW MEAN** over the last 10 logged points, with the
   step window quoted — never the single last sample, which carries full
   batch-to-batch variance.
   **The column is NATS, copied verbatim from `harvest.py`'s
   `train loss (tail-mean)` line.** `train/bpc` is already bits, so dividing it
   by ln 2 again is the double conversion that put the 2026-09-04 dropout x lr
   grid on the tab at 2.08x its true value (2.70 "nats" for a 1.30 run), and the
   unroll block of the same day was written from some other statistic that
   nobody can reproduce. Both were rewritten on 2026-09-05 with `CORRECTED`
   notes in the block headers. Cross-check any new train-loss cell against a
   finished neighbour: a value above the val loss is not a training run that
   underfits, it is a unit error.
6. **Write the row** (next section), then read it back.
7. **Per-site read-outs are DEFAULT-ON in unroll/truestate mode** (operator,
   2026-09-05, mirroring the adding-problem line): at every probe step
   (`--probe_every`, now **100**, which also sets the `u_norm`/`rho` cadence)
   `site_probe.py` logs, for each param in `--site_probe_params` (default
   `w_hh_0,w_hh_1,w_hh_2,encoder,dec_w`), `site/<param>/gnorm_off<j>` (raw
   per-site grad norm), `unorm_off<j>` (post-Adam per-site update norm),
   `share_off<j>` (contribution share w_j<u_j,A>/<A,A>, sums to 1, can be
   negative), `cos_off<j>` (merged-vs-raw cosine), with **offsets counted from
   the END of the window (1 = last timestep)**, plus a 5x3 figure as the
   `site_plots` image and a json snapshot under `site_plots/`. In a char-LM the
   raw norm is SMALLEST at offset 1 (that site carries one position's loss)
   and grows toward the front of the window -- the opposite of the adding
   problem -- while `unorm` stays flat: that pair is the optimizer working.
   `site_plots/ok = 0` plus `site_plots/error` in wandb means rendering failed
   (a box without matplotlib); the snapshot is still written first.

### The Row Format

Columns, in order: `config / run · seed n · train loss (tail-mean) · val loss
(best ckpt) · val bpc (best ckpt) · val acc (best ckpt) · val loss (final) ·
val acc (final) · wandb group · notes`. Every metric column is **`mean +- sd`
over the 4 seeds**; a bare number in one of them is a bug, not a shorthand. The
two `(final)` columns are not redundant: they are the selection-free comparison,
and they are what reveals that loss and accuracy peak at different steps.

Shared protocol goes in the **block header row, once** — never repeated per row.
Per-row notes carry only what changes interpretation.

`gsheets` traps that cost real writes here:

* **Pass cell values after `--`.** A value containing `/` or a leading dash is
  otherwise parsed as a flag: the command prints its help text, returns rc=0,
  and writes nothing. `Wrote 1 rows.` absent means the write did not happen.
* **Escape commas as `\,`** — the CLI splits cells on `,` and rows on `|`.
* **Resolve the tab by title.** The workbook holds dated backup tabs; a
  remembered gid writes into a frozen snapshot nobody reads.
* Read the range back and confirm each value landed in the intended column.

## The Double Last-Layer Dropout (found and fixed 2026-09-05)

**Every fused-baseline cell with `--dropout > 0` written before 2026-09-05
dropped the LAST layer's output twice.** `CharLM` applied `self.drop` after
every layer inside its layer loop, the last included, and then a second
`final_drop` on the same tensor when `--final_dropout 1` -- keep probability
(1-p)^2 on the decoder input: 0.25 for the blog recipe's p=0.5, 0.81 for the
grid's p=0.1. Both upstreams drop each layer's output exactly once (torch-rnn
adds `nn.Dropout` inside its per-layer loop, `LanguageModel.lua:58-60`; gpjt
puts one Dropout on the LSTM output), and `UnrollCharLM` always did exactly
that, so **the unroll-vs-baseline comparison at dropout 0.1/0.3 (rows 31-38
vs 16-27) was confounded**: the baseline was more regularised than its label.
Affected: blog rows 9-12 and grid rows 16-27 (+ their readings, rows 13 and
28). Unaffected: torch-rnn rows 4-6 (dropout 0), all unroll rows. Fix:
`final_dropout` now gates the single last-layer application in BOTH models
(default 1 = the upstream behaviour); `test_dropout_is_applied_once_per_layer_output_in_both_models`
counts the `F.dropout` calls. Reruns launched 2026-09-05 21:40Z by
`lg_fix.sh` (64 runs, groups `grid_*_fixdrop_20260905`, `blog_*_fixdrop_20260905`);
the reruns REPLACED rows 9-12 and 16-27 on 2026-09-05 23:4xZ (each row's note quotes
its pre-fix value; readings 13/28 and the unroll verdict in the reading row carry
`CORRECTED` / `RE-READ` paragraphs). What changed: the fix matters at high dropout
(blog p=0.5: 2.5882 -> 2.5348, so the blog recipe now BEATS torch-rnn's default by
0.043 instead of tying it; grid d0.4: 2.51-2.53 -> 2.49-2.51) and is inside noise at
p=0.1 (2.5003/2.4801/2.4730 -> 2.5126/2.4807/2.4712). New best baseline cell:
dropout 0.2 / lr 4e-4 = 2.4601+-0.0170 (row 21). The best unroll cell (row 31,
2.4637+-0.0263) still ties it.

The help text used to claim torch-rnn does not drop the last layer; it does.

## Tab Layout Of The Unroll Block (after 2026-09-05)

Rows 31-34 uniform weight (d0.1/d0.3 x lr 2e-4/4e-4), 35-37 uniform at dropout 0
(lr 2e-4/3e-4/4e-4), 38-39 the MEAN divisor control (`--unroll_mode mean`, divide
by sum w = n: lr 2e-4 still running toward the 200-epoch cap, lr 2e-3 = 2.5154
reproduces the sqrt cell at lr 2e-4), 40-41 per-site clip 0.02 on the row 31/32
recipe (`--site_clip`: neutral at lr 2e-4, +0.015 inside sd; never fires at lr
4e-4 where it is a pure seed replicate of row 32), 42-45 the 1/i weight, 46 the
reading. Rows were inserted with `insert-rows --range`, which shifts everything
below intact. The DEPTH-site sweep (`--site_index depth --depth_max {4,16,100}`,
lr 2e-4/4e-4, dropout 0.1, groups `unroll_depth<d>_d0.1_lr<lr>_20260905`) was
launched 2026-09-05 23:3xZ by `lu_depth.sh` and is not on the tab yet.

## Depth Sites: What Happened On The First Night (2026-09-05/06)

`--site_index depth --depth_max D` (`depth_sites.py`, exact VJP recurrence,
dropout masks replayed via `UnrollCharLM.forward(masks=...)`): depths 1..D are
sites, plus one remainder site. Measured on the 80GB box, 5 runs per card:
d_max=4 is FASTER than time sites (5 Adam sites instead of 100), 16 is ~1.5x,
100 is ~3.6x slower per step. **Uniform weight over depth bands fails at
D=100**: after 4 epochs val sat at 4.85 bpc, the unigram floor, in all 8 seeds
(stopped). Deep bands carry no signal but per-band Adam normalizes them to
O(1), so the merge is ~95 noise directions against ~5 signal ones. D=16
learned ~5x slower per epoch than time sites; D=4 at lr 4e-4 tracked time
sites at lr 2e-4 (a ~2x effective-lr shift from divisor sqrt(5) vs sqrt(100)).
The operator's answer is `--depth_weight inv_depth` (band b gets 1/b, orthow
divisor sqrt(sum 1/b^2)): groups `unroll_depthinv{100,16,4}_d0.1_lr{2e-4,4e-4}_20260906`,
running on the two 40GB boxes from 00:43Z. Uniform-weight D=4/16 keep running
on the 80GB box for the comparison.

## Per-Site Alignment: Why The Divisor Is sqrt(n) Late And ~n Early

`analyze_site_align.py` (run on the box with the venv python, read-only) takes
a checkpoint, the raw per-site gradients on a few train batches and the per-site
Adam updates rebuilt from the checkpoint's `site_opt` moments, and reports the
pairwise cosine structure plus **d\* = ||sum_i x_i|| / rms_i ||x_i||**, the
divisor that keeps the merged vector at one site's norm (sqrt(n)=10 if the
sites are orthogonal, n=100 if aligned). Measured 2026-09-05 (C=100):

| where | raw site grads g | per-site Adam updates u |
|---|---|---|
| seed-0 INIT | mean cos 0.84-0.90, d\* 78-94 (aligned) | no state yet |
| trained, dropout 0, lr 2e-4 (final) | mean cos 0.02-0.06 (b_0 0.14), d\* 17-25 (b_0 38) | mean cos ~0.01, **d\* 11.5-14.6** (b_0 19) |
| trained, dropout 0.1, lr 2e-4 (09-04 cell) | d\* 15-19 (w_hh_2 37) | d\* 10.6-13.5 (b_0 19) |

So the sqrt(n) divisor is about right once training has settled (the merged
update is 1.2-1.5x one site's, 1.9x for the bias), and ~9x too small at the
start, when every site pushes the same way. The finer per-(site, loss)
decomposition of `w_hh_0` (5050 terms) is essentially orthogonal: mean cos
0.001 overall and 0.001 within a site across losses; only same-loss terms of
adjacent sites align (cos 0.22 at lag 1, <0.02 past lag 10). Site t's gradient
is therefore a sum of ~(C-t) near-orthogonal pieces, which is why the raw
norm grows toward the front of the window. `--unroll_mode mean` (divide by
sum w = n) exists for the aligned regime; groups
`unroll_unmean_d0_lr{2e-4,2e-3}_20260905` are its first test.

**Dropout 0 for the uniform arm (rows 35-37, 2026-09-05)** is worse than 0.1
at every lr (2.5040-2.5401 bpc vs 2.4637), best lr 3e-4, early stop at 22-35
epochs; the no-unroll dropout-0 point is still untested.

## Open Question This Line Exists To Answer

The adding problem gives **one** supervised timestep, so early-step gradients
vanish and merge-rule reweighting has something to fix. Char-LM supervises
**every** timestep and already runs truncated (`seq_length` IS the window), so
the premise is weakened. Whether any unroll mechanism helps here is therefore a
NEW question, not a transfer of the adding-problem result. The per-position loss
profile (`pos/*`) is the readout: a flat curve means the carried state is doing
the work.

Note the mechanism code does not port for free — `unroll_util.py`'s zero-delta
trick is written for a single-layer vanilla RNN's `W_hh`. An LSTM's
`weight_hh_l0` is four stacked gate blocks, so its spectral norm is **not** the
recurrent Jacobian's; `metrics.py` logs each gate block separately for that
reason. `--model_type rnn` is the path that connects to the existing machinery.
