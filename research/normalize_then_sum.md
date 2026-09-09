# Weight sharing: first normalize, then sum

**The core research hypothesis is that shared weights should receive separately normalized call-site gradients before those updates are summed.** This page records the research owner's formulation. It is the intended optimizer story, not a claim that every implementation or benchmark already establishes it.

## Single-loss formulation

Ordinary autodiff accumulates contributions from every use of a shared parameter before the optimizer sees them. For shared parameter theta and call-site contributions g_i, the usual order is:

```text
g = sum_i g_i
update = Normalize(g)
```

Here Normalize denotes the optimizer's transformation, such as Adam's moment-based preconditioning or Muon's matrix update transformation; it does not necessarily mean unit Euclidean norm. The proposed order is:

```text
u_i = Normalize_i(g_i)
update = sum_i w_i * u_i / sqrt(sum_i w_i^2)
theta <- theta - learning_rate * update
```

Each contribution has its own optimizer state when the transformation is stateful. The model still has one shared parameter: separating gradients and optimizer state does not untie the forward weights. Autodiff may still compute the contributions; the change is to avoid losing their identities through accumulation before normalization.

## Distance weighting

**Weighting is an important part of the method in the owner's experiments.** A generally good choice so far is `w_i = 1 / n_i`, where `n_i` measures the call site's distance to the loss in the computation graph. Count the nearest relevant call as `n = 1`. Contributions nearest the loss usually deserve larger weights. Specify what constitutes one distance step for each architecture; this is not necessarily the number of primitive autodiff operations.

The empirical importance of weighting is part of the current research premise. This note does not assert a general theorem that inverse distance is optimal.

## Update-scale alignment

**Divide the weighted sum by `sqrt(sum_i w_i^2)` to approximately align its norm with the ordinary shared-weight optimizer's update scale.** If the normalized contributions have a comparable norm U and are pairwise orthogonal, the weighted sum has norm `U * sqrt(sum_i w_i^2)`. Dividing by that constant removes the increase predicted by this approximation.

Real contributions can be correlated and can have unequal norms, so the denominator is an approximate calibration, not exact norm matching. Check measured update norms when interpreting comparisons. Keep learning rate, clipping and weight decay conventions explicit so that these choices do not obscure the ordering effect.

## Multiple losses: group by relative distance

**With dense supervision, group contributions by call-to-loss relative distance before normalization.** In char-LM, the object is a call/loss pair, not merely an absolute timestep counted from the end of the sequence.

Let `g_(s,l)` be the contribution from shared-parameter call s to loss l, and let `d(s,l)` be their relative graph distance. Then the intended grouping is:

```text
G_n = sum_{(s,l): d(s,l) = n} g_(s,l)
U_n = Normalize_n(G_n)
update = sum_n w_n * U_n / sqrt(sum_n w_n^2)
```

Include the original objective's loss coefficients and reduction convention in `g_(s,l)`. Calls at different absolute positions but the same distance from their respective losses belong to the same group. First aggregating all downstream losses at each absolute call and normalizing those totals is a different experiment.

## Validation settings

The prototype settings are mazes and char-LM. Maze64 at 60k updates is the recommended fast maze recipe; Maze128 remains a later scale check. The larger candidates are Parcae, ELT and TRM on ARC-AGI-1. On 2026-09-07, the owner agreed to remove CoDi from the main plan because its joint teacher/student/distillation recipe complicates attribution. This experiment-selection decision does not stop any running job.

The priority backup candidates are ALBERT supervised fine-tuning and RAFT optical flow. The owner wants broadly recognizable baselines: CLRS and MoDL are deprioritized, and SimCLR is excluded. RAFT's recurrent gradient paths support the method, but its multiple supervised losses require relative-distance grouping and extra backward computation. See the [RAFT graph checks, compute audit and ELT DEV estimate](../archive/audits/20260907-raft-applicability-elt-dev.md).

ELT can use an author-code development scale for early screening, with its published large recipe reserved for confirmation. The estimated DEV80k baseline budget, with repeated FID moved out of training, is 2–3 hours centrally on v7-32, or about 6 hours including the owner's x2 allowance. This is a VAE-pipeline-anchored estimate, not a DEV training measurement. See the [Maze64 timing and original backup survey](../archive/audits/20260907-weight-sharing-backups.md) for the earlier investigation.

The central comparison is normalize-after-sum versus normalize-before-weighted-sum under matched data, forward sharing, training budget and update-scale conventions. Weighting, scale calibration and grouping are separate ablations needed to explain the result.

Related measurement: [baseline runtime and experiment selection audit](../archive/audits/20260907-baseline-runtime.md).
