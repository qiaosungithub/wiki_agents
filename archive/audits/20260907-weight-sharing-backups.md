# Maze64 turnaround, backup benchmarks, and ELT cost

Audited 2026-09-07. This follows the [initial timing audit](20260907-baseline-runtime.md)
and the [normalize-then-sum research premise](../../research/normalize_then_sum.md).
The owner has agreed to remove CoDi from the main validation plan. No training
jobs were launched, stopped, or reconfigured for this investigation.

## Decisions

Use **Maze64, 60k updates as the fast maze prototype**, keeping Maze128 for a
later scale check. The historical JAX runs support a roughly one-hour productive
turnaround and a 2–2.5-hour reservation with the requested x2 preemption allowance.
This is evidence from TPU runs, not a measured promise for the current H100 port.

The owner's follow-up narrows priority backups to ALBERT and RAFT. CLRS and MoDL
are deprioritized because the owner wants broadly recognizable settings; SimCLR
is excluded. The recipes below retain their technical provenance, while the
[follow-up audit](20260907-raft-applicability-elt-dev.md) owns the updated selection,
RAFT applicability and compute, and ELT DEV estimate.

Keep ELT as an expensive confirmation experiment, with a smaller author-code
development configuration for early screening. Its current cost is consistent
with the author's own wall timestamps; small parameter counts do not imply
small executed computation.

## Maze64: measured time and provenance

Read the live [maze64-clean spreadsheet tab](https://docs.google.com/spreadsheets/d/17pvrMbOKOKFiIa-eorO8Od12qc5JmrFCSXcXKeoe_u0/edit#gid=916430925)
and `EqR-refactored`, then downloaded original worker logs. Raw rows, log-source
paths, extracted effective configurations and timing calculations are saved in
[the evidence directory](../../../.weight_sharing_survey_20260907/).
[The analysis script](../../../.weight_sharing_survey_20260907/analyze_maze64.py)
uses checkpoint write-event epoch timestamps within individual attempts. These
intervals include periodic evaluation and saving, but exclude initial compilation,
queueing, restart gaps, and final standalone evaluation.

All measured maze rows below use board64, patch4, hidden128, H3/L4/L_layers1,
batch2048, float32, and 60k updates. The baseline and fixed SUM runs are documented
as v7-32 in the spreadsheet. The last2 run's archived queue entry independently
confirms v7-32. The RON worker log confirms eight processes and 64 logical TPU
devices; its exact accelerator generation was not independently recovered.

| Run | Optimizer arm | Measured checkpoint window | Wall steps/s | 60k extrapolation | With x2 allowance |
|---|---|---|---:|---:|---:|
| [280054628](http://xids/280054628) | Ordinary shared Muon, clip2 | 5k–60k, one attempt | 24.259 | 41.2 min | 82.4 min |
| [280405676](http://xids/280405676) | Bug-fixed per-call SUM, last1 | 5k–60k, one attempt | 23.203 | 43.1 min | 86.2 min |
| [281423049](http://xids/281423049) | Ordinary shared Muon + readout norm | 5k–60k, one attempt | 20.562 | 48.6 min | 97.3 min |
| [282338556](http://xids/282338556) | Per-call sqrt merge, last2 | 20.5k–60k, attempt4 | 15.549 | 64.3 min | 128.6 min |

For example, RON checkpoint5k was written at 2026-08-20 00:19:51.878 UTC,
and checkpoint60k at 01:04:26.736. That is 55k updates in 2674.858 seconds.
The last2 run independently gives 64.7 minutes per 60k from its first attempt's
checkpoint window. Its saves occur every 500 updates, versus 5000 in the earlier
rows; this difference and the changed backward depth prevent attributing its
whole overhead to optimizer normalization.

The ordinary baseline's launch-directory timestamp to terminal log write spans
47.4 minutes; fixed SUM spans 50.5 minutes; RON spans 57.9 minutes. These are
coarse launch-to-finish checks, including startup, and corroborate the checkpoint
estimates. The last2 run spans approximately 100 minutes across several attempts;
that is already affected by restarts, so it is not doubled again in the table.
For scheduling, round to **about 1 hour for baseline and 1–1.2 hours for the
historical per-site arms, then reserve 2–2.5 hours per run**. The exact proposed
inverse-distance implementation still needs a timing measurement.

### What the old table can and cannot establish

The tab contains informative Maze64 60k outcomes: RON shared Muon has 80.4%
random-unmask solution accuracy; the SUM entry 281584092 reports 91.1%; last2
sqrt 282338556 reports 88.8%. This suggests useful dynamic range at 60k. These
are historical spreadsheet results, not a fresh numerical reproduction or a
matched estimate of optimizer benefit: LR, weight decay, clipping, checkpoint
selection and EMA selection differ.

There are several separate invalid-comparison hazards:

- `EqR-refactored` row205 explicitly records the fix for stale `L_level` weights
  and `_equalize` behavior: detached and differentiable cycles must use the same
  shared forward weights. Earlier failed unroll sweeps do not establish a negative
  result for the proposed method.
- The `maze64-clean` tab includes Maze128 rows later in the sheet. Zero scores
  there are not evidence that Maze64 fails at 60k.
- The later postnorm / variance-preserving-merge block has activation explosions
  and changed residual equations. Exclude it when selecting a stable prototype.
- Early metric implementations accepted invalid painted cells. Later confidence
  sampling versus random unmasking also changes the reported metric substantially.
  Use one corrected scorer and a fixed sampler for all new comparisons.
- Best-of-four EMA, fixed EMA, 60k endpoints and best checkpoints are different
  selection rules. In particular, the older SUM and sqrt treatments are not
  automatically the owner's current inverse-distance-normalized update.

### Recommended small recipe

Use the existing offline 38.4M-maze corpus and stable readout-normalized geometry:
board64, patch4, hidden128, two heads, H3/L4/L_layers1, existing four-layer mask
head, and batch2048 for 60k updates. Keep the established stable residual equation
and disabled trainable halting. Start with last1 differentiation, preserving
five differentiable shared calls; last2 is a subsequent depth ablation. Both
optimizer arms must have identical forward computation and differentiation depth.

Keep data, noise, head, clipping and EMA policy fixed. Use random-unmask,
D16/B1/ss20, 1000 held-out mazes for the headline evaluation, and a fixed EMA
rate such as 0.9995. Evaluate a predetermined checkpoint or choose on a separate
validation set. Defer D64, sampler sweeps and multi-EMA selection to confirmations.
Use symmetric LR search budgets; the previous SUM winner's LR is not calibrated
for the new weighted/sqrt-normalized update. Clipping order and decoupled weight
decay must also match the intended definition. Do not reduce batch and steps
simultaneously as an unlabelled speed optimization.

The board-size change does not reduce the main token count: `(64/4)^2 =
(128/8)^2 = 256`. Width halves from the inspected Maze128 recipe's 256 to 128,
and the output grid shrinks, but attention does not gain a fourfold reduction in
token count. The 150k-to-60k schedule alone removes 60% of updates. The current
8-H100 Maze128 trace took 4.03 hours to reach 60k, versus 10.19 hours for the
complete 150k run. Thus a same-port fallback is approximately 8 hours including
x2 for Maze128/60k; the one-hour Maze64 evidence is from the historical JAX/TPU
implementation and cannot isolate the contribution of size, hardware and port.

## Backup survey: selection criteria

The shared parameter must participate in multiple differentiable calls during
training. Prefer established tasks, official code, accessible data and a terminal
supervised loss. Finite depth makes inverse distance and optimizer-state grouping
explicit. Popularity alone does not compensate for a recipe that changes the
scientific question. The ranking below is an experiment-design judgment.

### First: ALBERT-base-v2 supervised GLUE fine-tuning

ALBERT is an established cross-layer-sharing Transformer, with official pretrained
models. The base-v2 configuration has hidden768, 12 layers, one hidden group and
one inner-group layer: one Transformer block is called 12 times. Full supervised
fine-tuning on SST-2 or MNLI supplies a terminal classification loss and avoids
joint teacher/student training. It tests fine-tuning optimization rather than
pretraining from scratch. Small parameter storage does not remove its 12-layer
forward cost. Sources: [paper](https://arxiv.org/abs/1909.11942),
[author repository](https://github.com/google-research/albert),
[model configuration](https://huggingface.co/albert/albert-base-v2/blob/main/config.json).

There is an actual public ALBERT SST-2 training log: batch32, sequence64,
LR3e-5, five epochs, 10,520 updates, one GPU, best dev accuracy 92.55%.
It does not record elapsed training time or GPU model. This is a concrete
reproduction target independent of the original paper's best GLUE score.
Source: [training log](https://huggingface.co/textattack/albert-base-v2-SST-2/blob/425babba49140dc3547a886d7808f2a37c10ef2d/log.txt).

For a modern implementation, Hugging Face's official `run_glue.py` supports
ALBERT. Its generic batch32/sequence128/three-epoch recipe would give roughly
6.3k SST-2 updates or 36.8k MNLI updates. These are proposed ALBERT settings,
not the five-epoch log above. The README reports **BERT-base** times of 26m06s
on SST-2 and 2h35m23s on MNLI using one Titan RTX; these only establish a
related workload's cost scale, not measured ALBERT throughput. Source:
[official training example and time table](https://github.com/huggingface/transformers/blob/main/examples/pytorch/text-classification/README.md).

Recommendation: first reproduce the five-epoch SST-2 target; use MNLI as the
larger follow-up if needed. Use the same pretrained initialization in both arms
and several seeds, since a small dev set can obscure optimizer differences.

### Investigated: CLRS algorithmic reasoning with a recurrent GNN

CLRS supplies established algorithmic tasks and reference neural processors.
Start with Bellman–Ford, then BFS and Dijkstra, using a shared MPNN/PGN processor.
This covers reasoning and length generalization with a smaller input structure
than pixel mazes. Sources: [benchmark paper](https://arxiv.org/abs/2205.15659),
[official repository and dataset protocol](https://github.com/google-deepmind/clrs).

The current official runner supplies hidden128, batch32, 10k training iterations,
LR1e-3, training lengths 4/7/11/13/16, and `hint_mode=none` as a supported option.
Select `processor_type=mpnn` explicitly: the current default is a triplet model.
Use one algorithm per run and unchunked differentiation. With no hints, supervise
the algorithm's final output; this is explicitly a different benchmark task from
the hint-supervised setting. Preserve the chosen length/data policy in both arms.
The canonical benchmark includes larger test inputs, typically size 64. Source:
[official runner](https://github.com/google-deepmind/clrs/blob/master/clrs/examples/run.py).

No trustworthy elapsed time for this exact small configuration was found.
10k small-graph updates make it a plausible low-cost candidate, not a verified
one-hour run. For budgeting after a synchronized pilot, use
`reserved hours = 2 * 10000 / measured_steps_per_second / 3600`, adding compile
and evaluation costs. One outer iteration trains each selected algorithm, so
selecting all 30 does not cost the same as selecting one.

### Investigated: MoDL MRI reconstruction

MoDL is an established model-based reconstruction method. It alternates a
five-layer CNN and data-consistency solves for ten iterations, sharing the CNN.
The paper uses final-image MSE; Equation 14 explicitly sums contributions from
the shared CNN calls. This is unusually close to the proposed optimizer story.
Table V reports **10.6 hours of GPU training**, or 21.2 hours with an artificial
x2 allowance. The inspected timing passage does not specify a GPU model, and
this is not a current H100 timing. Source:
[paper, objective and gradient equations; Table V](https://arxiv.org/html/1712.02862v3).

The author releases a 3GB dataset, including precomputed masks and coil maps:
360 training slices from four subjects and 164 test slices from a fifth. The
original implementation targets TensorFlow1.7, so porting risk is higher than
for ALBERT. Source: [author code and dataset description](https://github.com/hkaggarwal/modl).

The training script defaults to `K=1`, which would not exercise iteration-wise
sharing. Explicitly use `K=10`. For `K>1`, it restores a single-iteration model;
share the same warm-start checkpoint between optimizer arms and count its cost
separately. This is a staged initialization, without joint teacher/student
distillation. The script's defaults include 50 epochs and batch 1: 18k updates for
360 slices, plus warm-start training. A from-scratch variant would be a separate
recipe. Source: [training script](https://github.com/hkaggarwal/modl/blob/master/trn.py).

Recommendation: strongest application-domain extension, after matching a small
reference reconstruction and its gradients. Keep CG differentiation, CNN batch
normalization and any shared regularization scalar explicit in the treatment.

### Additional reserves

| Domain / baseline | Training-time sharing and cleanliness | Cost / reason for lower priority |
|---|---|---|
| Molecular property regression: QM9 recurrent MPNN | The official PyG example reuses one NNConv and GRU three times, then predicts a scalar with supervised regression. Set2Set also contains recurrent sharing. | Hidden64/batch128/300 epochs is approximately 260k updates, not a 10k-step toy. The example computes target normalization before splitting data; change to training-only statistics and label that correction. No elapsed time recovered. [Code](https://github.com/pyg-team/pytorch_geometric/blob/master/examples/qm9_nn_conv.py). |
| Optical flow: RAFT | Recurrent learned updates provide real shared calls. The code detaches coordinates each iteration and supervises several flow predictions, so preserve this graph and use relative-loss grouping. | The official schedule includes 100k Chairs, 100k Things, 100k Sintel, and 50k KITTI updates on two GPUs. A Chairs-only or small-model test needs an explicit label; it is not the final multi-stage paper result. [Graph](https://github.com/princeton-vl/RAFT/blob/master/core/raft.py), [schedule](https://github.com/princeton-vl/RAFT/blob/master/train_standard.sh). |

Do not automatically select ordinary diffusion training: the usual single sampled
timestep does not differentiate through the inference denoising chain. DEQ is
also less direct: its implicit backward does not expose a finite unrolled list of
call-site contributions in the same way; replacing it with ordinary unrolling
changes the method. Source: [DEQ implementation](https://github.com/locuslab/deq).

## ELT: independent cost audit

The requested subagent independently inspected the executed model, original and
local events, author development modes and paper. Its
[full report](../../../.baseline_timing_20260907/elt_cost_followup.md) and
[independent calculations](../../../.baseline_timing_20260907/elt_cost_independent_timing.json)
retain the source paths.

The large diffusion recipe uses 1024 tokens, actual width 2048, effective depth 32,
batch 512 and 500k updates: 256M image presentations. Its 16N×2L model has about 1.08B
parameters. A 4N×8L model reduces parameter count while retaining 32 executed
layers. The inspected code uses BF16 matrix operations, flash attention,
rematerialization, and online frozen-VAE encoding. ILSD reuses the teacher prefix
rather than running a second complete trunk. Removing it simplifies the objective
but does not imply a twofold speedup.

The timing discrepancy is a demonstrated metric bug: the old timer resets after
blocking `jax.device_get`, omitting the queue drain. Original author events give
37.43 seconds per 100 updates, or 2.672 steps/s, despite a scalar of 3.863. That
extrapolates to 52.0 hours for 500k before evaluation pauses. Local stock gives
about 46.7 hours including normal saves; 4N×8L gives 47.2 hours. Original hardware
was 256 v5e chips and local hardware is 32 v7 chips, so this is not a controlled
implementation speed comparison. There is no evidence here of an order-of-magnitude
port regression, and no device profile sufficient to rule out smaller inefficiencies.

The paper's diffusion “Small” model is still width 2048 and 1.1B parameters, with
16 **untied** layers. The tabulated looped diffusion variants keep 32 effective
layers. Smaller MaskGIT S/B models exist in the paper, but their tabled inference
loop counts alone do not establish a complete cheap training recipe. Source:
[paper tables and appendix](https://arxiv.org/html/2604.09168v1#A2).

| Smaller option | Geometry / training budget | What is established |
|---|---|---|
| Author-code DEV | 1N×8L, width 512, batch 256, 80k updates | Executable author development mode; no exact published score or measured runtime found. |
| Author-code STAGE | 1N×16L, width 1024, batch 512, 200k updates | Executable intermediate mode; no exact published score or measured runtime found. |
| Original 16N×2L checkpoint at 100k | Width2048, batch 512; retain 500k schedule/curriculum | Measured-rate projection 9.34 hours, x2 = 18.7 hours. This is an intermediate checkpoint, not a converged 500k baseline. |

Recommendation: screen at DEV scale, initially preserving the author 1N×8L shape.
If capacity limits learning, consider an explicitly derived 2N×4L variant with
the same eight executed layers. Disable DEV's default repeated 50k-image FID while
screening. Decide separately whether to keep ILSD with relative-distance grouping
or use final-loss-only in both arms. A new small recipe does not inherit the
paper's FID target. The DEV trunk's total matrix work is roughly 1/650 of the full
PROD budget, but online VAE/input overhead makes this unsuitable as a wall-time
speedup estimate. Small-model runtime remains unmeasured.

For the current validation plan, keep Parcae and TRM as the main larger recipes,
ELT as a staged-cost candidate, and ALBERT and RAFT as priority reserves. The
follow-up audit evaluates RAFT's actual gradient paths and additional computation.
