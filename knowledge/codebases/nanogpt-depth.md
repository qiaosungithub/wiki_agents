# nanoGPT call/loss diagonal

Own checkout `~/work/nanogpt_depth/`, copied from lyy's nanoGPT and
tokengrad/depth code. Type 2 research code. Start with its `README.md`,
`MATH.md`, `EXPERIMENT_STATUS.md`, `RESULTS.md`, `WEIGHT_SWEEP_RESULTS.md`,
`LINEAR_SWEEP_RESULTS.md`, and `DEPTH_METRICS.md`. The source-copy fingerprint
is `UPSTREAM_COPY.json`; historical GPU run evidence is archived read-only under
`lyy_evidence/`. Chapter 1 is the mechanism and the setting, and Chapter 2
records what the sweeps have found. How to run a configuration against it is the
[nanogpt-depth-runs skill](../../harness/skills/nanogpt-depth-runs/SKILL.md).

---

## Chapter 1 — The Setting And What The Metrics Mean

### The gradient contract

**The first band `G1 = sum_j dL_j/dtheta_j` is parameter use and loss at the
same token position; the causal forward is unchanged.** Its attention backward
retains the local Q, K and V Jacobian blocks, and historical K/V values still
enter the local query derivative. Lyy's old gate froze attention probabilities
and incorrectly removed the Q/K part of this band, so do not reintroduce it.
`depth/call_diagonal.py` implements the band efficiently; `test_call_diagonal.py`
checks it against independent explicit per-position parameter deltas in FP32/FP64
on CPU/CUDA. The supported experiment uses dropout 0.

### The two-band optimizer

**Two independent Adam states normalize `G1` and `full-G1`, then combine as
`(u1 + w*u_rest)/sqrt(1+w*w)`, default w=.5.** Structural first-band-only
coordinates carry an explicitly zero remainder and divisor 1; do not infer their
membership from numerically nonzero Adam moments. `--expand_vectors=1` (default)
adds bias and LayerNorm scale/bias to the two-band treatment; `0` leaves those on
ordinary Adam. Token/position embeddings and the tied output head always stay
unexpanded, excluded by parameter identity. Nonzero-WD code applies one decoupled
matrix decay per step and no vector decay.

### The reference configuration

**The reference is the approximately 30M model, not the separate 124M run.**

| | value |
|---|---|
| model | ~30M: 6L/6H/384 |
| data | FineWeb-Edu, 500M train / 5M val tokens, GPT-2 BPE |
| shape / budget | T256/B32, 4000 updates, warmup 200 + cosine |
| optimizer | AdamW betas(.9,.999), wd0, no clipping |
| numerics | FP32, dropout 0 |
| data fingerprints | `DATA.json` |

Historical depth runs did not log train loss or save checkpoints, so do not
invent a historical train number.

### What the metrics mean

**All metrics are nats/token, and validation selects both the LR and the
checkpoint, so it is not an untouched test split.** The logged columns are train
tail-100, best and final val, a fixed-batch train eval, best-minus-final, plus
the group / chart / stagedir / logdir.

---

## Chapter 2 — What The Experiments Have Found

### A sound baseline comes first

**The user requires a sound baseline before any treatment experiment.** The
four-seed LR neighborhood check is recorded in `baseline_gate.json`; its scope is
the tested LR grid at fixed budget, not an optimizer-wide optimum. Muon has not
been established as a baseline for this line.

### The weight and linear-weight sweeps

**Every method seed tested so far stays worse than its paired baseline.** Both
sweeps ran four seeds per cell with zero decay and no separately tuned method LR.

| Sweep | Grid | Result |
|---|---|---|
| weight | w = .2 / 1 / 2 × vectors 0 / 1, fixed LR .0012, WD 0 | weight 1 is the best tested method weight in both vector modes |
| linear weight | starts {0, .5} → ends {1, 2} × both vector modes | best cell 0.5->2 vectors0, val 4.8329 ± .0281; no linear mean beats the corresponding fixed-1 reference |

The linear schedule interpolates w between update 1 and update 4000; both Adam
states accumulate even at weight 0, and it reproduces constant-w behavior bitwise
against the frozen source.
