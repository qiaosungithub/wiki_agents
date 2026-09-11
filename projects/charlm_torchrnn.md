# char-LM — torch-rnn reproduction (science line)

Character-level language modelling on tiny-shakespeare, reproducing
**`jcjohnson/torch-rnn`**. The purpose is a credible dense-supervision LM
setting in which to test this group's RNN mechanism work, whose home is the
adding problem (`rnn_unroll_adding.md`). Two chapters carry what stays true —
the setting and what each metric means (Chapter 1), and how to run research
against it (Chapter 2) — and a third records what the experiments have found so
far (Chapter 3).

---

## Chapter 1 — The Setting And What The Metrics Mean

### Which repo, and where everything is

"char-RNN" is ambiguous on the web; the one we reproduce is
**`jcjohnson/torch-rnn`** — Adam, a learned embedding, a 0.8/0.1/0.1 sequential
split.

| Thing | Path |
|---|---|
| Code | `~/work/charlm/` (`data_prep.py`, `data_loader.py`, `model.py`, `metrics.py`, `train.py`, `test_data.py`; unroll: `unroll_model.py`, `unroll_optimizer.py`, `unroll_util.py`, `site_probe.py`, `test_unroll.py`) |
| Interpreter on the box | `~/work/charlm/.venv/bin/python` (see Chapter 2 for why the bare `python3` fails) |
| Launcher | `~/work/charlm/run_official.sh` — the torch-rnn default, every flag spelled out, not inherited |
| Upstream Lua mirror (read-only) | `~/work/torch-rnn-upstream/` |
| Native docs | `~/work/charlm/README.md` — measured config table, deliberate divergences, exact logging keys |
| Compute | the 4×A100 boxes (SSH in `../gcp_gpu_ssh.md`). `~/work/charlm` + `.venv` + prepared data live on `qiaos-4a100-3` (80GB, the main one), `qiaos-4a100` and `qiaos-4a100-2` (40GB). The cloudtop copy is the source of truth; md5s must match before a launch |
| W&B | project `charlm-torchrnn-baseline`, entity `zhh24-massachusetts-institute-of-technology` |
| Results tab | EqR workbook `17pvrMbOKOKFiIa-eorO8Od12qc5JmrFCSXcXKeoe_u0`, tab **`charlm-torchrnn (qiaos)`** (resolve BY TITLE) |

### The measured configuration

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
| baseline val bpc (official recipe, 4 seeds, best ckpt) | **2.5775 ± 0.0227 bpc** |
| baseline val acc (same) | 0.4987 ± 0.0090 |
| cost | ~1 min/seed on one A100-80GB (3.0 ms/step, 78 MB) |

**Report against the unigram floor, not the uniform one.** A model that has
learnt only letter frequencies already reaches 4.7742 bpc.

**There is no official torch-rnn validation loss — do not go looking for a
target number.** The repo publishes only speed and memory over the first 100
iterations. The baseline is what we measure, comparable only to runs on this
same split. Do not import an lr or a schedule from `awd-lstm-lm` either: that is
a tuned recipe (paper Table 6), but for a different dataset and model scale.

### The split, and why `val` is "selected on" but not "trained on"

The byte boundaries are upstream's; the roles are ours.

| Slice | Role here | Upstream called it |
|---|---|---|
| first 80% | `train` | train |
| middle 10% | **unused** (kept so boundaries stay identical; `--eval_sel` to measure it) | val |
| final 10% | **`val`** — never trained on; the online eval split | test (upstream never touches it) |

**The checkpoint is selected by the lowest online val loss — upstream's own
protocol — so `val` was never TRAINED on but WAS SELECTED on, and those are
different claims.** Picking the best of ~18 checkpoints buys an optimistic bias
whose size is not knowable in advance, so three numbers are logged and none is
derived from another:

| Key | Model | Meaning |
|---|---|---|
| **`val_best/*`** | selected checkpoint | **the protocol number, the headline** |
| `val_final/*` | model at the step budget | selection-free comparison |
| `val_best_minus_final_bpc` | — | the bias, measured per run |

**Never quote the headline without the bias term beside it.** At this budget it
is −0.0022 ± 0.0021 bpc, negligible because the lr decays to 1.95e-6 and the
model stops moving well before the end — a property of THIS schedule, to be
re-checked whenever it changes.

`data_prep.py` carries `schema_version = 2` and refuses a directory written
under the old `train/val/test` naming (where "val" was the middle slice);
loading it silently would put every number on the wrong bytes.

### Accuracy is a secondary metric

**Judge a run by train and val loss; accuracy is a supporting signal only.**
Loss and accuracy do not peak at the same step, so a checkpoint chosen on loss
is not the accuracy-optimal one (one seed selected on loss read 0.4852 acc
against 0.5039 for its final model). `val acc (best ckpt)` and `val acc (final)`
both stay in the tab for that reason, but neither drives the verdict.

### Upstream quirks reproduced deliberately, both behind flags

* **`--adam_reset_on_decay 1`** (default): `train.lua` replaces the whole
  `optim_config` table on each decay, so **Adam's m/v are discarded every 5
  epochs**. `0` decays in place and keeps the moments.
* **`--grad_clip_mode clamp`** (default): element-wise clamp to ±5, **not** a
  norm clip. `norm` is what most modern code means by "grad_clip 5".

The default schedule takes lr from 2e-3 to **1.95e-6 by epoch 50 (÷1024)**. For
arm comparisons calibrated on `u_norm`, use a constant lr (`--lr_decay_factor
1.0`) and treat decay as its own variable.

### Known, explained divergences from upstream

| Thing | Upstream | Here | Why |
|---|---|---|---|
| parameters | 242,945 | 243,969 | PyTorch `nn.LSTM` carries both `bias_ih` and `bias_hh` (+4H/layer). Arithmetic only. |
| token ids | 1-indexed (Lua) | 0-indexed | bijection; loss identical, **checkpoints NOT interchangeable** |
| gate order | (i,f,o,g) | PyTorch (i,f,g,o) | only affects the forget-bias fill, written to the f-slice **by meaning** |

---

## Chapter 2 — Running Research Against This Line

### Use the venv python on the box

**On the box run `~/work/charlm/.venv/bin/python`** (a `--system-site-packages`
venv; wandb 0.29.0, matplotlib, pytest). The bare `python3` has NO wandb, and
started from `~/work/charlm` it imports the `./wandb` LOG directory as an empty
namespace package: `AttributeError: module 'wandb' has no attribute 'init'` is
that, not a broken install.

### The logging pipeline — one cell = one W&B group = 4 seeds = one row

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

### Reading the verdict off the tab

**Judge a run by its train loss and val loss relative to neighbouring rows** —
there is no absolute target (Chapter 1). A run's headline is `val bpc (best
ckpt)`; keep the `(final)` columns beside it as the selection-free comparison.

### The row format

Columns, in order: `config / run · seed n · train loss (tail-mean) · val loss
(best ckpt) · val bpc (best ckpt) · val acc (best ckpt) · val loss (final) · val
acc (final) · wandb group · notes`. Every metric column is **`mean +- sd` over
the 4 seeds**; a bare number is a bug. Shared protocol goes in the **block header
row, once**; per-row notes carry only what changes interpretation. The
spreadsheet-write mechanics (the `gsheets --` trap, comma escaping, resolve-by-
title, read-back) are generic and owned by `../research/result_logging.md`.

### Logging detail

Use `--logging_detail compact` by default; `full` enables the legacy
prediction / hidden / spectral / site diagnostics. Diagnostic failures must be
visible without aborting training, and historical W&B records must never be
mutated to resemble the current schema. `charlm/README.md` owns the exact keys
and clipping semantics.

---

## Chapter 3 — What The Experiments Have Found

### The question this line exists to answer

**Whether an unroll mechanism helps here is a NEW question, not a transfer of the
adding-problem result.** The adding problem gives ONE supervised timestep, so
early-step gradients vanish and merge-rule reweighting has something to fix.
Char-LM supervises EVERY timestep and already runs truncated (`seq_length` IS the
window), so that premise is weakened. The per-position loss profile (`pos/*`) is
the readout: a flat curve means the carried state is doing the work.

The mechanism code does not port for free: `unroll_util.py`'s zero-delta trick
is written for a single-layer vanilla RNN's `W_hh`. An LSTM's `weight_hh_l0` is
four stacked gate blocks, so its spectral norm is **not** the recurrent
Jacobian's; `metrics.py` logs each gate block separately for that reason.
`--model_type rnn` is the path that connects to the existing machinery.

### Best cells so far

- **Overall best: 1/depth `d_max=4` = 2.4242 ± 0.0139 bpc** (lr 2e-4).
- Baseline best: dropout 0.2 / lr 4e-4 = 2.4601 ± 0.0170.
- Best time-site unroll: 2.4637 ± 0.0263 — ties the baseline.

### Per-site alignment: the divisor is sqrt(n) late, ~n early

The per-site merge divides the summed update by a divisor that keeps the merged
vector at one site's norm: `d* = ||sum_i x_i|| / rms_i ||x_i||`, which is sqrt(n)
if the sites are orthogonal and n if they are aligned (n = 100 here).

**Once training has settled the sites are near-orthogonal (`d*` ≈ 11–25), so the
sqrt(n) divisor is about right; at init they are aligned (mean cos 0.84–0.90,
`d*` 78–94), so sqrt(n) is ~9x too small.** `--unroll_mode mean` (divide by
sum w = n) exists for that early aligned regime. A finer per-(site, loss)
decomposition of `w_hh_0` is essentially orthogonal (mean cos ~0.001); only
same-loss terms of adjacent sites align (cos 0.22 at lag 1), so site t's gradient
is a sum of ~(C−t) near-orthogonal pieces, which is why the raw norm grows toward
the front of the window.

### Depth sites: deep bands must be down-weighted

`--site_index depth --depth_max D` makes depths 1..D sites (plus one remainder),
via an exact VJP recurrence with dropout masks replayed. Cost: `d_max=4` is
faster than time sites (5 Adam sites instead of 100), 16 is ~1.5x, 100 ~3.6x
slower per step.

**Uniform weight over depth bands FAILS at D=100** — val sits at the unigram
floor (4.85 bpc) in every seed, because the deep bands carry no signal but
per-band Adam normalizes them to O(1), so the merge is ~95 noise directions
against ~5 signal ones. **The fix is `--depth_weight inv_depth`** (band b gets
1/b, ortho divisor sqrt(sum 1/b²)): it yields the best cell on the tab, and the
weight on the deep bands matters more than the band count.

### The double last-layer dropout bug (rule)

**Each layer's output must be dropped exactly once; `final_dropout` (default 1 =
upstream behaviour) gates the single last-layer application in BOTH models.**
Before the fix, `CharLM` with `--dropout > 0` dropped the last layer twice (once
inside the layer loop, once as `final_drop`), giving keep probability (1−p)² on
the decoder input and silently over-regularising the baseline relative to its
label — which confounded the unroll-vs-baseline comparison at dropout 0.1/0.3.
Both upstreams drop each layer's output once, and `UnrollCharLM` always did too.
`test_dropout_is_applied_once_per_layer_output_in_both_models` counts the
`F.dropout` calls. The fix matters at high dropout (blog p=0.5: 2.5882 → 2.5348)
and is inside noise at p=0.1.
