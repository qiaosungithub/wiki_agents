# nanoGPT call/loss diagonal

Own checkout: `~/work/nanogpt_depth/`, copied from lyy's nanoGPT and
tokengrad/depth code. Type 2 research code. Start with its `README.md`,
`MATH.md`, `EXPERIMENT_STATUS.md`, `RESULTS.md`, `WEIGHT_SWEEP_RESULTS.md`,
`LINEAR_SWEEP_RESULTS.md`, and `DEPTH_METRICS.md`.
The source-copy fingerprint is `UPSTREAM_COPY.json`. Historical GPU run
evidence is archived read-only under `lyy_evidence/` in that checkout.

## Gradient contract

The first band is `G1 = sum_j dL_j/dtheta_j`: parameter use and loss at the
same token position. The causal forward stays unchanged. Its attention
backward retains the local Q, K and V Jacobian blocks. Historical K/V values
still enter the local query derivative. Lyy's old gate froze attention
probabilities and incorrectly removed the Q/K part of this band.

`depth/call_diagonal.py` implements this efficiently; `test_call_diagonal.py`
checks it against independent explicit per-position parameter deltas in
FP32/FP64 on CPU/CUDA. Supported experiment uses dropout0.

Two independent Adam states normalize G1 and `full-G1`, then combine updates
as `(u1 + w*u_rest)/sqrt(1+w*w)`, default w=.5. Structural first-band-only coordinates have
an explicitly zero remainder and divisor1; do not infer their membership from
numerically nonzero Adam moments. `--expand_vectors=1` is the default and
includes bias/LayerNorm scale/bias; `0` leaves those on ordinary Adam.
Token/position embeddings and the tied output head always stay unexpanded,
excluded by parameter identity.

## Experiment and records

Reference is the approximately30M model, not the separate124M run: FineWeb-Edu
500M train/5M val tokens, GPT-2 BPE; 6L/6H/384, T256/B32, 4000 updates,
FP32/dropout0, AdamW betas(.9,.999), wd0, no clipping, warmup200+cosine.
Dataset fingerprints are in `DATA.json`. Historical depth runs did not log
train loss or save checkpoints; do not invent a historical train number.

The user requires a sound baseline before treatment experiments. The
four-seed LR neighborhood check is recorded in `baseline_gate.json`; its
scope is the tested LR grid at fixed budget, not an optimizer-wide optimum.
Muon has not been established as a baseline for this line.

The September9 weight sweep completed all24 new runs: w=.2/1/2, vectors0/1,
four seeds each, fixed LR.0012 and WD0. Weight1 is the best tested method weight
in both vector modes, but every method seed remains worse than its paired
baseline. See the checkout's completed report, not controller PIDs, for results.
No weight has a separately tuned method LR. Every existing run has zero decay;
nonzero-WD code applies one decoupled matrix decay per step and no vector decay.
Do not relaunch the completed manifests. The watcher exited SWEEP_ALL_VERIFIED.

The subsequent linear-weight follow-up is COMPLETE: starts{0,.5} to ends{1,2},
both vector modes, four seeds each. All32 runs passed audits and are recorded in
rows20–27. See LINEAR_SWEEP_RESULTS.md and linear_sweep_progress.json in the
checkout; linear_sweep_index.json owns the exact eight manifests.
Source is stages/linear_weight_20260909_v1/source.
w interpolates between update1 and update4000; both Adam states accumulate
even at weight0. Resume derives w from the absolute optimizer update. Old
constant behavior was checked bitwise against the previous frozen source.
The best linear cell was0.5->2 vectors0 (val4.8329±.0281); no linear mean beat
the corresponding fixed1 reference. Do not relaunch completed controllers.

One confirmed configuration = four seeds = one W&B group = one sheet row.
W&B entity `zhh24-massachusetts-institute-of-technology`, project
`nanogpt-depth`. Shared workbook
`17pvrMbOKOKFiIa-eorO8Od12qc5JmrFCSXcXKeoe_u0`, dedicated tab
`nanoGPT (qiaos)` (explicitly requested by the user). Resolve by title and
re-read its live header; `../research/result_logging.md` governs writes.
Metrics are nats/token: train tail100, best/final val, fixed-batch train eval,
best-minus-final, plus group/chart/stagedir/logdir. Validation selects LR and
checkpoint, so it is not an untouched test split.

`stage.py` creates a hash-verified immutable source snapshot. `launch.py`
records exact commands, GPU/PID and output paths and rejects busy GPUs.
`harvest.py` archives exact manifest jobs; `audit_remote.py` verifies successful
exit, checkpoint-reload equality and online W&B history. A PID or result file
alone is not completion. `LOAD_FROM`/`--resume` restores both band moments,
ordinary optimizer and batch RNG; never reuse an existing output for a cold run.

GPU hosts and exact zones come from the current launch manifests. At the
initial experiment, host2 and host3 were used; `qiaos-4a100` was occupied by
unrelated RAFT jobs and the guard correctly aborted. Recheck live occupancy.
SSH used `--ssh-flag=-oIdentityAgent=none` to bypass a stalled local SSH agent
without disturbing shared authentication services. See `../gcp_gpu_ssh.md`.
