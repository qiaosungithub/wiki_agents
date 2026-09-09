# Baseline runtime and experiment selection, 2026-09-07

This is a dated measurement, not standing infrastructure guidance. The research
formulation lives in [normalize_then_sum.md](../../research/normalize_then_sum.md).
The raw downloads and calculations are in
[.baseline_timing_20260907](../../../.baseline_timing_20260907/).

## Planning convention

**The planning column multiplies productive runtime by two, as requested.** It
is a provision for preemption, restart and lost work, not a measured universal
preemption rate or a guarantee of queue availability. Each row is one run/seed,
not an optimizer sweep. These hardware allocations are different and must not
be compared by wall time alone. No training jobs were launched or changed for
this audit.

| Setting and budget | Hardware | Productive elapsed time | Planning time, x2 |
|---|---|---:|---:|
| Maze128, current Torch baseline, 150,000 steps, batch 2048, f32 with TF32 | 8 H100 | 10.2 h, measured complete run including periodic and final eval | 20.4 h |
| Maze128, 60,000-step checkpoint of that same run | 8 H100 | 4.03 h, measured | approximately 8.1 h |
| char-LM, current LSTM L3/H512, B100/T100, baseline Adam, existing early-stop protocol | 1 A100 per seed | 171–234 s (2.85–3.90 min), four completed seeds | 5.7–7.8 min per seed |
| CoDi GPT-2 LoRA, GSM8K-Aug recipe, 40 epochs / 119,920 scheduled steps | 8 H100 | 8.3 h from productive throughput; historical start-to-finish about 9.6 h with interruptions | approximately 17–20 h |
| Parcae-140M, 11.2B tokens / 21,362 steps | 8 H100 | 8.7–9.1 h | approximately 18 h |
| ELT, 500,000 steps, batch 512, stock 16N x 2L or 4N x 8L | v7-32 | 46.7–47.2 h of training | approximately 94 h / 3.9 days |
| ELT, 1N x 32L, same training budget | v7-32 | approximately 50.7 h, extrapolated from early training | approximately 101.5 h / 4.2 days |
| TRM ARC-AGI-1, 518,070 steps, batch 768 | 8 H100 | approximately 31.4 h, including routine checkpoint saves | approximately 63 h / 2.6 days |

TRM's separate completed final-evaluation job took about 11.6 minutes from
process entry through exit, or 19.3 minutes from its directory's launch
timestamp through exit. ELT's final 50k-image FID is separate from the training
figures: the older evaluation record describes roughly 100 minutes, but the
recently corrected paper evaluation protocol has not been timed here. Do not
present that old evaluation as a measured duration for the corrected protocol.
CoDi's table is training only; its final answer-generation evaluation was not
timed in this audit.

## Evidence and independent checks

### Maze128

**Use the fixed production run, not the obsolete slow embedding-backward run.**
XID `286980299`, run directory
`/cns/si-d/home/qiaos/eqr_data/logs/eqr-maze128/xid_286980299_20260906_003636_eqr_maze128_row4_150k_v2`.
Read its `sanity/286980299_1_att2197337548233_rank0.jsonl` directly. It has
1,501 training records, starts step 1 at 00:45:53 UTC, reaches step 150000 at
10:55:01, and exits successfully after final evaluation at 10:57:33. The
monotonic timestamps give 10.1943 h through final evaluation. Median productive
speed is 4.41365 steps/s; wall throughput is 4.10424 steps/s including the
periodic overhead. World size 8, per-rank batch 256 and TF32 are recorded in
the same file.

Independent check: XID `287079915`, continuation from the reference's 50k
weights, logs 50100 through 52000 over 432.467 s, or 4.3934 steps/s. This
confirms the fixed production speed on another job. The completed cold-start
run is a runtime measurement; it does not by itself certify numerical
reproduction of the JAX trajectory.

The older JAX reference XID `282061906` reports median 13.7338 steps/s across
473 intervals in `logs/rank_3_attempt1.log`. Its log records **64 logical JAX
devices**, versus 8 GPUs for the Torch run. The exact accelerator generation
was not recovered in this audit, so this is not an equal-hardware speed
comparison. That run's checkpoint directory also contains its later extension
to 150k; the first attempt's declared 60k budget does not describe its complete
history. The obsolete Torch run at about 392 samples/s predates the embedding
backward fix and is excluded.

### char-LM

Use the saved raw W&B run summaries in
[source_snapshot.json](../../../charlm/figures/row21_vs_row60/source_snapshot.json),
group `grid_d0.2_lr4e-4_fixdrop_20260905`, configuration `mode=baseline`,
LSTM L3/H512, dropout 0.2, lr 4e-4, B100/T100. Runs `mj36jh40`, `v3uiir7g`,
`1d2g4e91`, `aobfvkx2` have runtimes **225, 234, 214, 171 seconds**, and stop
at **3115, 3649, 3827, 4005 steps**, respectively. These are completed runs
under early stopping, not full 200-epoch costs. Their reported steps/s and
step counts independently recover approximately the same elapsed times.

The smaller official L2/H128 baseline is a different recipe; its roughly
one-minute runtime in the project guide should not be substituted for this
current baseline.

**The baseline is cheap, but relative-distance decomposition is appreciably
slower.** The decoder-corrected completed runs in
[final_results.json](../../../charlm/sweeps/depth_decoder_fix_20260906/final_results.json)
have runtimes 1104–1277 s for depth_max=1, 1320–1435 s for depth_max=4,
2317–2960 s for depth_max=20, and 4239–5963 s for depth_max=100. Thus depth 4
is about 22–24 min per seed; full depth is about 71–99 min per seed. The
depth cutoff describes gradient grouping/decomposition; it does not mean
shortening the forward sequence to four characters. Keep the remainder policy
and matched baseline explicit when using a short-depth pilot.

### CoDi

Baseline XID `285339247`,
`/cns/si-d/home/qiaos/eqr_data/logs/codi-torch/xid_285339247_20260831_220921_codi_repro40_trainmode`.
The direct `metrics.jsonl` download ends at step 119920. Across 6,206 logged
positive-speed records after step 1000, median sps is **4.004**, with 10th/90th
percentiles **3.964 / 4.015**. `119920 / 4.004 / 3600 = 8.3195 h`.

Independent wall check: attempt 1's launcher artifact is timestamped
2026-08-31 22:19:21; the final worker log is timestamped 2026-09-01 07:57:05,
about 9.63 h later. There were six recorded training attempts. The raw
`rank_100_attempt5.log` also gives the same approximately 4 steps/s over a
long 66020–109580 segment. Do not concatenate repeated steps across attempts
and interpret the resulting record count as the scheduled training budget.

### Parcae

Baseline completion XID `284813218` resumes the shared checkpoint chain from
step 9216. Its process log is under
`/cns/is-d/home/qiaos/lyy_parcae_runs/logs/parcae-torch/xid_284813218_20260830_014011_parcae-140m-torch-repro-resume9216/logs/rank_0_attempt5.log`.
The long productive attempt logs steps 10241–21361. Across 10,361 records
after step 11000, median throughput is **0.684166 steps/s** after converting
tokens/s with `256 * 2048` tokens/step. This yields **8.673 h** for 21362 steps.

Independent check: the preserved checkpoint file timestamps under
`/cns/is-d/home/qiaos/lyy_parcae_runs/parcae-140m-torch/steps/` give
**0.683–0.685 steps/s** across consecutive unaffected 1024-step intervals.
The two much slower intervals contain interruptions and are excluded from
productive speed, then covered by the requested x2 planning allowance.
The chain takes 11 h 14 min from step 1024 to step 21361 including those gaps.
A separately documented 1536-step throughput control XID `285685523` gives
0.654–0.667 steps/s, supporting a rounded **9 h** budget.

### ELT

The 16N x 2L stock chain lives at
`/cns/qo-d/home/qiaos/eqr_data/logs/elt-dit/xid_285906137_20260902_141116_elt_stock_v732`.
Its final long TensorBoard event file was produced by resumed XID `286985731`.
Decoded event wall timestamps give **420600 → 499999 in 26689.307 s**, or
**2.97494 steps/s**, yielding **46.686 h** for 500k steps. This is a 7.4-hour
window near completion, not a microbenchmark. Median scalar throughput in
that file is 2.99230 steps/s.

Independent early-window wall check: the first stock event file gives
**200 → 13700 at 2.97698 steps/s**. Its median scalar speed is 4.39204,
which overstates the wall speed across that window; use timestamps for
planning. The full historical chain spans September 2 through September 6,
roughly 4.3 calendar days including interruptions.

New 4N x 8L baseline XID `287228190` has its actual config and first event
file downloaded directly. It gives **200 → 9500 at 2.94035 steps/s**, while
the independent scalar median is **2.94587**, yielding **47.236 h** for 500k.
The actual config confirms batch 512, 500000 steps and distill_weight=1.0.

For 1N x 32L, the saved measurements at
[launch_plan.json](../../../.elt_results/unroll_20260907/launch_plan.json)
record **2.73761 steps/s at step 5700** for XID `287229539`. The 50.7-hour
figure is an early extrapolation, not a completed full run or an independently
timed long window.

Raw TensorBoard scalars here are TensorProto field 8, not simple_value field 2.
[analyze.py](../../../.baseline_timing_20260907/analyze.py) decodes both and
asserts that each event file yields usable speed records. The decoded 4N x 8L
scalar agrees with the independently saved launch-time measurement.

### TRM on ARC-AGI-1

Use the ordinary-optimizer baseline continuation XID `285254715`,
`/cns/si-d/home/qiaos/eqr_data/logs/trm-torch/xid_285254715_20260831_163859_trm_arc1_torch_real_v7a`.
Read **all six rank-0 attempt beacon files**, preserving attempt identity.
Within-attempt checkpoint timestamps give **4.56685–4.58223 steps/s**, median
**4.57701**, over independent windows from 5k to 70k steps. These rates
already include routine checkpoint writes. `518070 / 4.57701 / 3600` is
**31.442 h**. The continuation covers 280000–518070; it is not a full run from
scratch. Its predecessor is XID `285023898`; do not combine both branches'
overlapping steps as additional training.

The separate completed full-split evaluation XID `285543022` has rank-0
entry at 14:05:02 and successful exit at 14:16:35 on September 1. Its
previously recorded score is pass@2=0.4225. This audit directly re-read the
timing beacons, not the original score payload.

## Experiment selection

**Recommendation: make Parcae, ELT and TRM the three main larger settings, and
retain CoDi as optional supplementary evidence.** Together they cover language
modelling, visual generation and abstract reasoning. Three settings can provide
adequate breadth; the strength of the result still depends on repeated seeds,
matched baseline tuning, weighting ablations and measured update scales.
Do not omit existing negative results merely because CoDi is deprioritized.

CoDi's teacher and student are tasks of a shared model, with explicit-CoT CE,
implicit-CoT CE and representation distillation jointly optimized. Changing
normalization before merging can therefore change the balance between those
objectives as well as the balance among recurrent calls. This is an attribution
cost, not evidence that CoDi is an invalid benchmark. See the
[CoDi paper](https://arxiv.org/abs/2502.21074).

**ELT also has self-distillation, so removing CoDi does not make the remaining
set uniformly free of auxiliary objectives.** The
[ELT paper](https://arxiv.org/abs/2604.09168) uses intermediate-loop students
and a maximum-loop teacher; the actual local baseline logs both student and
distillation losses. Moreover, the current weighted implementation's own
[record](../../../.elt_results/unroll_20260907/README.md) says that main and
student contributions share a visit's optimizer state and use the same
absolute-visit weight. That differs from the newly stated relative-distance
multi-loss formulation. Resolve or explicitly label that distinction before
claiming an exact test of the common rule. A no-ILSD control could separately
measure whether an optimizer effect persists without this auxiliary objective;
it would be an ablation, not the original ELT recipe.

For turnaround, use char-LM's existing depth-4 decomposition as a roughly
22–24-minute pilot, followed by full-depth confirmation. Keep Maze128 as a
medium-cost validation: its current 150k Torch run occupies eight H100s for
about ten hours, which is a poor inner loop for rapid iteration. This is a
prioritization recommendation; it does not authorize changing existing runs.
