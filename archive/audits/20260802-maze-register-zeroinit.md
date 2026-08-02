# Maze register ablation — zero-init kills the run, and the metric that says so

Read-only investigation, 2026-08-02. Evidence: the three runs' mirrored
`logs/rank_*.log` under their own checkpoint buckets, their staged config
snapshots under `experimental/qiaos/eqr_jax_final_stages/`, and the
`step_150000` checkpoints read back with orbax. Backs the register and
`lm_loss` rules in `../../projects/eqr_jax.md`.

---

## 0. TL;DR

Three `maze-150k` runs, v7-32, 150000 steps, all COMPLETED — no preemption, no
restart, no traceback. The staged configs differ by **one scalar**:

| XID | run | `puzzle_emb_*` |
|---|---|---|
| 276313731 | REG | `ndim 128, len 16, trainable true, init_std 0.0` |
| 276314506 | LOUD | identical except `init_std 0.0883883476` (= 1/sqrt(128)) |
| 276314162 | NOREG | `ndim 0, len 0, trainable false` |

REG never solves a single maze — train OR test — in 150000 steps. LOUD and
NOREG both undergo a sharp grokking transition around step 13000. The single
differing scalar between REG and LOUD makes this a clean one-variable ablation,
so the attribution is **initialisation**, not the register implementation.

---

## A. What actually failed

`all/lm_loss` (periodic eval, test split) is the curve that shows it:

| step | REG | LOUD | NOREG |
|---|---|---|---|
| 5000 | 0.2901 | 0.2534 | 0.2643 |
| 20000 | 0.2976 | 0.0602 | 0.0668 |
| 50000 | 0.3327 | 0.0704 | 0.0650 |
| 100000 | 0.3127 | 0.0870 | 0.0811 |
| 150000 | **0.3326** | 0.1092 | 0.0970 |

REG starts at 0.290 and RISES to 0.333. It never descends.

Exact accuracy, tail window 140k–150k (interval means over 100 logged points):

| run | exact | token acc | `train/steps` |
|---|---|---|---|
| REG | **0.0059 ± 0.0038** | 0.9584 | 16.00 (pinned at `halt_max_steps`) |
| LOUD | 0.3717 ± 0.0669 | 0.9420 | 12.54 |
| NOREG | 0.2544 ± 0.1008 | 0.9419 | 13.92 |

REG's shape is "96% of cells right, 0% of boards right", and it holds on the
TRAIN split too — 1000 puzzles seen ~110000 times each. This is not a
generalisation failure; the model never entered the phase transition.

## B. The register table is NOT stuck — the "zero is a stationary point" theory is wrong

Read directly out of the checkpoints (`params/inner/puzzle_emb`):

| checkpoint | std | norm |
|---|---|---|
| REG @ 10000 | 0.0506 | 0.585 |
| REG @ 20000 | 0.0578 | 0.669 |
| REG @ 150000 | **0.0689** | 0.788 |
| LOUD @ 150000 | 0.0456 | 0.517 |

`opt_state/mu` and `opt_state/nu` for that leaf are both non-zero. The table is
in `params`, is differentiated, and grows. REG's final register magnitude is in
fact LARGER than LOUD's — so the mechanism cannot be "it never moved".

## C. What the failure correlates with: the q-head never learns to halt

With registers on, `q_head` reads `z_H[:, 0]`, which is a register slot, not a
board cell. At init that slot's input embedding is exactly zero under
`init_std=0`.

`max_q_logits` over training (REG stays negative for effectively the whole run):

| run | q-logit trajectory | crosses 0 at | exact acc at that step |
|---|---|---|---|
| REG | −5 → **−15** by 10k, still **−0.47** at 150k | **146300** (peak +0.48) | 0.006 at 150k |
| LOUD | −5 → −12 by 5k, rises after 6k | ~12600 | 0.09 → 0.44 by 15.9k |
| NOREG | −5 → **−27** by 5k, rises after 8k | ~13500 | 0.02 → 0.25 by 16k |

`q_halt_loss` collapses to 1e-8 for REG (a dead head) and `train/steps` stays
pinned at 16 for the entire run. REG's `q_halt_precision`/`recall` peak at 0.50
against 0.96/0.97 for LOUD and 0.92 for NOREG — it does eventually flicker, ~4000
steps before the end, far too late to matter.

For LOUD and NOREG, the q-logit crossing zero and exact accuracy lifting off
happen within the same few hundred steps.

NOREG diving to −27 (deeper than REG's −15) and still recovering shows the
q-logit depth is not itself the cause — what differs is whether the head's
input carries signal during the early steps.

**Status: INFERRED.** The correlation is tight and the config diff is one
scalar, but the causal chain (zero slot → no q-head signal → symmetry unbroken
→ missed critical period) is not directly proven. Two cheap experiments would
settle it: (a) re-run REG under a different seed; (b) keep `init_std=0` but
point `q_head` at `z_H[:, puzzle_emb_len]`, the first real board cell.

## D. `len: 16` is one register, not sixteen

`_input_embeddings` computes `pad = puzzle_emb_len * hidden_size - ndim`
= 16*128 − 128 = 1920, and `jnp.pad`s the table row before reshaping to
`(16, 128)`. Only slot 0 holds table content; slots 1–15 are constant zeros
with no gradient path. They do still shift every real token's rope index. Both
REG and LOUD share this, so it does not explain the difference — but a writeup
calling these runs "16 registers" is wrong.

## E. Metric trap this investigation walked into

The first pass at this analysis reported "REG has the LOWEST loss" from
`train/lm_loss` (REG 0.111 vs LOUD 0.187 / NOREG 0.194) — the opposite of the
truth, and contradicted by the chart the user was reading. Three separate
errors, all now rules in `../../projects/eqr_jax.md`:

1. **Wrong key.** `train/lm_loss` (train split, ~1500 points) is not
   `all/lm_loss` (test split, 30 points). The log holds five keys ending in
   `lm_loss`.
2. **Wrong divisor.** Loss keys are per-row SUMS; `process_metrics` divides
   keys ending in `loss` by `global_batch_size` (768), but the hand computation
   used `count` (halted rows only, ~6.5), inflating the number ~100x. A
   `*_avg` key is additionally a per-process sum — the measured ratio of
   `lm_loss_avg` to `train/lm_loss` was ~96 = 768/8 processes.
3. **Incomparable protocol.** Even computed correctly, `train/lm_loss` is
   measured at each run's own ACT depth. REG is pinned at 16 steps while LOUD
   halts at 12.5, so REG buys a lower training loss with ~28% more compute per
   row. The two numbers do not belong in one column.
