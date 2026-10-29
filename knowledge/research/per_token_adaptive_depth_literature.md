# Screened Literature: Per-Token Adaptive Depth (Early Exit, Halting, Adaptive Loop Count)

Owns the screened paper list for one question: can each token decide how many layers or loop passes to run, and how
should the K/V of an exited token be served, especially in looped (weight-shared, recurrent-depth) LMs. The sibling page
[looped_kv_literature.md](looped_kv_literature.md) owns K/V sharing across loop passes. The experiments live on
[midtrain_loop_adaptation.md](midtrain_loop_adaptation.md), whose §9 finding (injected, random-depth checkpoints can read
earlier tokens' last-loop K/V zero-shot) is the precondition for per-token exit. Screening method and tier meanings:
[literature-review skill](../../harness/skills/literature-review/SKILL.md). Per-paper audits (C1-C10, Q1-Q6), the
parent re-check table and the synthesis live in `~/work/lit-review/adaptive_depth/`: `G1..G6_*.md`, `REUSED.md`, and
`SYNTHESIS.md`, which holds the re-check table. The Chinese review report is
`~/work/reports/per_token_adaptive_depth_review.html` (and `.pdf`).

Chapter 1 is what the tier A and B papers establish; Chapter 2 is the tiered list; Chapter 3 is what is open and what to
run first on our models.

---

## Chapter 1 — What The Tier A And B Papers Establish

**No mature method shows per-token adaptive depth giving real wall-clock savings at unchanged reasoning quality, but
each component has credible support, and an injected, random-depth looped model is the favourable case.** Near-lossless
savings reported anywhere are modest, about 10-25% of loop passes (Huginn about 25% at 16 loops; Ouro about 12-24% at 4
loops). No paper measures MATH under per-token exit.

| Component | What works | What fails |
|---|---|---|
| Deciding the depth | Training-free convergence rules on random-depth looped models. KL of successive outputs (Huginn, A, MT-Bench only). Normalized state change on Huginn beats fixed depth at equal mean depth on GSM8K (about 27 vs 20.5 at 8 of 16 loops) and reaches full quality at about 12 (2608.09444, B). On Ouro the state-change rule is within 1-2 points of a trained gate (MMLU, figure only) | ACT / PonderNet mixture-loss heads: they run 7.6-7.9 of 8 iterations (2610.32246, B) or collapse to one loop when attached post hoc. Joint training of a decider collapsed for Think-at-Hard (B). At equal average compute, trained per-token depth has not beaten fixed depth on GSM8K (ETD adaptive part) |
| K/V of an exited token | Reuse its last computed per-layer K/V, i.e. a reader at pass d reads token j's pass min(d, e_j) ("deepest available"). Huginn zero-shot; 2610.32246 measures it keeps quality at 0.5-2% extra decode time; Huginn single-slot on GSM8K (2608.09444) | Hiding the exited token (MoR-style depth-matched attention): Think-at-Hard ablation -8.5 avg; FlexiDepth (A) GSM8K 0.657 -> 0.366; 2610.32246 reverses its lead. Re-projecting the frozen exit state through deeper layers ("state copying"): breaks in a looped model (2610.32246, up to +0.375 BPB) and degrades with scale in untied stacks (FREE, A) |
| Exact alternative | Deferred completion or verification (FREE, EE-LLM, LayerSkip, AdaDecode): quality-exact | Saves no FLOPs; latency gain only at batch 1 |
| Real speed | Depth-wise refill batching (continuous depth batching) reaches 96-99% (Ouro) and 83-96% (Huginn) of the FLOP bound, 1.3-1.5x end to end (2608.09444, B), but at operating points that cost about 6-8 GSM8K points, with replayed exit traces | Lockstep batching pays the deepest token: 1.62-1.69x measured vs 2.25x ideal at 32 sequences (2610.32246); early-exit gains under 2% at batch 8 (DREX, C). Native per-token skipping is slower than dense (FlexiDepth -15 to -21%, measured by vSkipper, B; Think-at-Hard 1.43x slower at batch 1) |
| Retraining for exit | Layer dropout plus early-exit loss gives self-speculative decoding (LayerSkip, A) | It cost Llama3-8B 9 GSM8K points (54.2 -> 45.0) and 5 MATH points |

- In a looped model, re-projecting an exited token's state and reading its deepest K/V coincide, because every pass
  uses the same W_K / W_V; the CALM and FREE copy-versus-recompute results from untied stacks do not transfer directly.
- Report realized depth per pass, threshold and batch size, not average depth (2610.32246), and output length under
  natural stopping (vSkipper: a skipping checkpoint generated 185% more GSM8K tokens). A high exit rate can mean depth
  stopped mattering rather than a good rule (Readout Blind Spot, C).
- Separate the gain of adaptive depth from the gain of the training change: about half of Think-at-Hard's GSM8K gain
  survives when inference is forced to depth 1.

---

## Chapter 2 — Tiered List

**Tier A is core evidence; tier B is unvetted concurrent work and must be flagged as such in the sentence that cites
it; tier C and D stay out of reviews.** Each row names the claims not to cite.

| id | Paper | Tier | Use | Do not cite |
|---|---|---|---|---|
| 1603.08983 | ACT | A | Founding halting mechanism | An LM gain (its LM result is null); robustness to the ponder penalty |
| 1807.03819 | Universal Transformers | A | Per-position ACT in a weight-shared Transformer | Any compute saving (its code computes halted positions) |
| 2107.05407 | PonderNet | A | Probabilistic halting formulation | LM applicability (none tested) |
| 1910.10073 | Depth-Adaptive Transformer | A | Per-token exit with state copying; source of "deepest available" | "76% fewer blocks" beyond IWSLT; any latency |
| 2207.07061 | CALM | A | Confidence exit with Learn-then-Test calibration; state propagation | Speedups as batched-serving numbers |
| 2310.05424 | FREE | A | Synchronized parallel decoding; state copying degrades with scale | SPD as a compute saving |
| 2312.04916 | EE-LLM | A | Early-exit training system; exact KV by recomputation or pipelining | "2x or higher without quality loss" |
| 2404.16710 | LayerSkip | A | Early exit plus self-speculative decoding | "No accuracy drop" for the training recipe |
| 2404.02258 | Mixture-of-Depths | A, borderline | Trained router, causal-predictor fix for top-k | "50% faster sampling" (a FLOP proxy) |
| 2503.23798 | FlexiDepth | A, borderline | Skipped tokens must stay readable (no-KV ablation) | "Full performance while skipping 8 of 32 layers" |
| 2410.20672 | Relaxed Recursive Transformers | A | Origin of continuous depth-wise batching; TinyLlama conversion | "2-3x throughput" (simulated with oracle exits); lossless exit |
| 2507.10524 | Mixture-of-Recursions | A | Trained router with recursion-wise caching | 2.06x as end-to-end (KV time excluded); beating vanilla at equal FLOPs |
| 2502.05171 | Huginn | A | Zero-shot KL exit with deepest-available K/V | Adaptive exit as harmless in general (MT-Bench only) |
| 2510.25741 | Ouro | A | Trained exit gate; state-change rule close to it | Exit-gate savings as realized (its released code runs all loops) |
| 2310.07096 | Sparse Universal Transformer | B | Halted state used as K/V in training and inference | Any realized saving |
| 2506.03700 | AdaDecode | B | Lossless per-token exit by deferred completion; GSM8K 1.48-1.60x at batch 1 | Superiority to speculative decoding |
| 2609.37062 | vSkipper | B | Engine-level skipping +4 to +11% saturated throughput; output-length caution | Knee latency gains as user-facing |
| 2511.08577 | Think-at-Hard | B | Trained per-token decider on math; duo-causal K/V ablation | Margins over its loop baselines; "minimal overhead" as latency |
| 2510.07358 | Encode-Think-Decode | B for fixed depth; adaptive part C-grade | Fixed-depth GSM8K scaling with loop count | "+36% MATH"; adaptive compute savings |
| 2610.12582 | Elastic Latent Recurrence (Koi) | B, KV part only | Last-loop K/V at 4B; per-request loop count | Anything about per-token depth |
| 2608.09444 | Continuous Depth Batching | B | Only real per-token-exit throughput in looped LMs; Huginn zero-shot exit on GSM8K | 1.3-1.5x as lossless; Ouro speedups (timed in a KV layout where Ouro scores 0.23%) |
| 2610.32246 | Do Halting Heads Really Save Compute? | B | Realized vs average depth; hide / reuse / copy K/V comparison | "Halting heads do not save compute" in general (BPB only, no depth-wise batching) |

### Tier C (appendix only) and tier D (ignored)

| id | Paper | Tier | Reason |
|---|---|---|---|
| 2307.02628 | SkipDecode | C | Monotone exit schedule keeps all K/V; speedups never timed |
| 2604.18396 | River-LLM | C | "Early exit" speedup is 4-bit quantization |
| 2512.15705 | DREX | C | Early-exit gains vanish at batch 8; rebatching recovers 2-12% |
| 2410.13184 | Router-Tuning | C | Sequence-level attention skipping; GSM8K plot only |
| 2410.20022 | Dynamic layer selection | C | Linear controllers no better than a constant |
| 2502.13842 | Inner Thinking Transformer | C | Non-causal routing never tested in generation |
| 2603.01914 | AdaPonderLM | C | Our exact K/V rule trained in, loss-neutral, but only 5-7.5% savings |
| 2604.22782 | Stochastic KV Routing | C | Random-source training to read another layer's K/V; QA only |
| 2607.14427 | Per-Token Fixed-Point Convergence | C | Zero-shot KL exit on a 57M random-depth model, teacher-forced K/V, single seed |
| 2603.08391 | Adaptive Loops and Memory | C | "Adaptive" loop runs all iterations |
| 2605.09165 | Sparse Layers Critical to Scaling Looped LMs | C | Early exit on a fixed-depth model: large PPL cost, FLOPs only |
| 2609.03379 | RecurTrace | C | Per-sequence halting; ACT and PonderNet collapse post hoc |
| 2610.18174 | Looped Reasoning Finishes Earlier (QRR) | C | Puzzle solver, not an LM |
| 2606.24898 | Readout Blind Spot | C | Toy-scale caution about exit rates |
| 2506.21103 | Learning to Skip the Middle Layers | C | Negative result at 124M |
| 2610.09013 | Ragged KV | C | min(d, e_j) on Ouro: about 24% decode depth near-losslessly, no batched speedup |
| 2603.21365 | TIDE | D | Claims a speedup while its own limitations say every layer runs |
| 2509.23314 | Two-Scale Latent Dynamics | D | Plot-only headline; text latency contradicts its own figure |
| 2510.13876 | What Layers When (GateSkip) | D | Baseline rows contradict the stated equal-budget protocol |
| 2609.15160 | T-LoopFormer | D | Baseline table is a shifted copy of LoopFormer's |

---

## Chapter 3 — What Is Open, And What To Run First

**On our injected, random-depth looped TinyLlama, two things decide whether per-token exit is worth building: the
GSM8K / MATH depth curve below the trained depth, and whether reading an exited token's shallower K/V is free.** Our
in-house last-loop result covers only the deeper direction. Every earlier token ran all R passes, so a reader at pass
t <= R read K/V at least as deep as its own pass. Early exit adds the opposite case (reader at pass d > e_j). The
literature finds that direction more forgiving: Ouro tolerates it although it collapses under last-loop reads (Ragged
KV), and Huginn and sampled-depth models tolerate it. It is unmeasured on our checkpoints.

| Order | Experiment | Why |
|---|---|---|
| 1 | GSM8K / MATH per_loop at k = 1, 2, 3, 4 (and 8), plus the teacher-forced per-token oracle depth | The curve bounds every exit rule. AdaLN 7+8+7 is flat from 4 to 10 passes, so savings can only come below the trained depth |
| 2 | Zero-shot exits in real token-by-token decode: successive-pass KL, normalized state change, top-1 stability. Fill with min(d, e_j), with hiding as a negative control, plus random per-token exits and shuffled depths as controls | Tests the shallow-direction fill and the criteria at once. Compare against fixed depth at equal mean depth, and against the random-depth model run at the realized depth |
| 3 | Only if fill costs quality at high exit rates: fine-tune with per-token random depth and frozen-exit K/V (a `where` mask as in AdaPonderLM) | min(d, e_j) is causal in depth, so it trains exactly in parallel. Unlike the last-K/V order, it needs no sequential training |
| 4 | Only if zero-shot criteria trail the oracle: an exit head on a frozen backbone, trained with a per-step loss and early-stop prior or by oracle imitation, with the threshold calibrated by Learn-then-Test on held-out data | Learned halting is fragile; ACT / PonderNet mixture losses fail on LMs |
| 5 | Wall clock: batch-1 decode first; depth-wise refill scheduling only if near-lossless savings reach about 30% of core passes | With 7+7 non-looped layers, an 8-layer core at R = 4 is about 70% of per-token compute, so 25% fewer passes is about 17% less compute. Lockstep batching erases most of it |
