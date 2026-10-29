# Screened Literature: Looping As Per-Token K/V Or Fast-Weight Refinement

Owns the screened paper list for one idea: in a weight-shared (looped) decoder, a loop pass refines
the current token's K/V, later tokens read only the final K/V of earlier tokens (per-token recurrence),
and this generalizes to looping as a fast-weight update (the test-time-training view). Standard looping,
where pass t reads the pass-t K/V of every token, is a Jacobi iteration over (token, pass); last-K/V
per-token recurrence is the Gauss-Seidel order. The experiments live on
[midtrain_loop_adaptation.md](midtrain_loop_adaptation.md). How papers were screened and what the
tiers mean: [literature-review skill](../../harness/skills/literature-review/SKILL.md). The Chinese
review report on KV handling in looped LMs is `~/work/reports/looped_kv_cache_literature_review.html`.
Per-paper audits live in `~/work/lit-review/looped_kv_fastweight/`: `G{1..5}_*.md` hold the rubric
checks, `E{1..4}_notes.md` the tier, maturity, training and inference notes, and `DISCARD_VERIFY.md`
the primary-source re-check of the decisive numbers. The same directory holds our own measurements:
`OURO_VS_HUGINN.md` (the Ouro-1.4B pilot probe), `inhouse_kv_sharing_results.md` (13-checkpoint
factorial) and `inhouse_kv_zeroshot_generation.md` (GSM8K / MATH generation); they are summarized in
[midtrain_loop_adaptation.md §9](midtrain_loop_adaptation.md#9-last-loop-kv-sharing). Per-token adaptive depth (exit
rules, the K/V an exited token exposes, realized speedups) is owned by
[per_token_adaptive_depth_literature.md](per_token_adaptive_depth_literature.md).

Chapter 1 is what the tier A and B papers establish; Chapter 2 is the tiered list; Chapter 3 is where
the idea is still open.

---

## Chapter 1 — What The Tier A And B Papers Establish

**Whether a looped model can read only the last loop's K/V zero-shot depends first on input injection
and then on training: four independent groups agree on the phenomenon, and our own factorial (one seed,
1.1B, short answers only) points to injection as the cause.** Models trained with random depth,
truncated backprop or damped updates tolerate it zero-shot (Huginn 2502.05171; Towards II 2610.06833
and BeNice 2610.31633, both B); all three inject the input on every loop. Ouro (2510.25741, fixed 4
loops, every-loop supervision, whole stack looped with no injection) collapses once generations or
contexts are long: MATH500 75.9 to 45.9 and RULER-16K 77.5 to 7.0 (HLA 2610.07940, B), GSM8K 0.794 to
0.000 (LLA 2607.15456, B), Core 54.6 to 25.2 (BeNice). Ouro's own Table 14 (GSM8K 78.92 to 78.85)
holds only for short few-shot answers. Within injected architectures, fixed-depth training halves GSM8K
under sharing (Towards II: 50.6 to 21.2), and removing injection raises the sharing penalty from
+21.9% to +232% (Towards II Table 18).

- In-house ([midtrain_loop_adaptation.md §9](midtrain_loop_adaptation.md#9-last-loop-kv-sharing)):
  without injection (ETD, like Ouro) the loop-entry pass's K/V cannot be replaced by the last pass's.
  With random depth the exact last-K/V loss rises by about 10 nats, concentrated in pass-1 layers 0-1,
  which is the entry-cell signature of our Ouro pilot probe and of BeNice's Parcae diagnosis; with fixed
  depth it rises by 0.23 nats, spread over all pass-1 layers.
- With injection (AdaLN, CtL) the only cost is about 0.03 nats for fixed-depth, last-pass-only
  supervision, and either multi-exit supervision or random depth removes it. So for injected models
  every-loop supervision acts like random depth, and Ouro fails because it has no injection, not
  because of its objective. Our injected random-depth checkpoints stay within about 1 point on GSM8K /
  MATH under zero-shot last-K/V generation, for answers of at most 256 tokens.

**Methods that work either train the cross-loop read pattern in or keep loop-specific information.**
Trained in: MoR (2507.10524, recursion-wise caching or first-recursion sharing, 0.7 pt cost), PLT
(2510.24824, first-loop K/V plus a 64-token per-loop window, exactly parallel in training), MELT
(2605.07721, B, gated K/V refined across loops, 3.98x less KV), BeNice. Kept loop information: a
low-rank codec of the loop trajectory (LLA), a latent cache plus an exact window (HLA). Only about 6%
of K and 17% of V variance lies along the loop axis (LLA).

**Prefill stays parallel and depth-matched; reading refined K/V of past tokens is a decode-time
sequential dependency, and training it exactly is expensive.** MELT's chunk-wise training is about 10x
slower per token and its fully parallel variant fails (MATH-500 55.0, below the untrained 58.0). LCKV
(2405.10637) trains a read-the-top-layer-K/V dependency with about 7 no-grad sweeps plus 2 grad sweeps
(about 2.7x training time); HLA's repeated passes cut the KL to sequential decoding from 5.6e-3 to
2.9e-5. Kirsch (2610.33360, B, lowest weight, at most 228M) measures +0.052 nats between parallel
training and sequential serving and closes about 80% of it with a K/V consistency loss; extra parallel
sweeps did not close it. Implicit LMs (2502.07827) train Jacobi and serve Gauss-Seidel with 97.6 to
97.7% greedy agreement at 2 to 4x training cost.

**KV savings usually show up as batch capacity, not decode speed; PLT is the exception.** MELT decodes
at 8.5 vs Ouro's 13.5 tok/s, and Ouro's released code caches all 4 loops whatever its exit gate says.

**Reading earlier tokens' most-processed state buys state tracking, at a training-time cost.** Feedback
Transformer (2002.09402): code execution 33.7 to 99.1, random walk 68 to 100, at 2.2 to 3.5x training
time; top-layer-only memory works as well as mixing all layers.

**Several sequential inner steps per token on a fast weight increase expressivity.** DeltaProduct
(2502.10297) takes n_h delta-rule steps per token (adaptive n_h is future work); MesaNet (2506.05233)
solves each token's regression with conjugate gradient, adaptive steps only at inference; in TTT
(2407.04620 Fig 7) and LaCT (2505.23884 Fig 8b), updates closer to per-token beat large batches or
chunks. A gradient-trained linear layer is exactly linear attention over its training pairs
(2202.05798), so a K/V cache is the training set of a fast weight; this is exact only for unnormalized
linear attention.

---

## Chapter 2 — Tiered List

**Tier A is core evidence; tier B is unvetted concurrent work and must be flagged as such in the
sentence that cites it; tier C and D stay out of reviews.** Each row names the claims not to cite.

### Looped-LM K/V handling

| id | Paper | Tier | Use | Do not cite |
|---|---|---|---|---|
| 2502.05171 | Huginn | A | Released model; K/V slots `i mod k`; random-depth training makes K/V shareable | Its own KV-sharing parity (MT-Bench only, underpowered) |
| 2507.10524 | Mixture-of-Recursions | A | Per-token depth with recursion-wise caching ((N_r+1)/2N_r of the cache) or first-recursion sharing (1/N_r) | "Beats vanilla at equal FLOPs" (its Tables 7 and 9 disagree) |
| 2510.25741 | Ouro | A | The field's standard looped checkpoints; fixed-depth training | "Matches 12B models"; its own MATH500 numbers; Table 14 as a general result |
| 2510.24824 | Parallel Loop Transformer | A, borderline | First-loop K/V plus gated window, exactly parallel training, near non-looped latency; adopted by LPT and LoopCoder-v2 | "Beats a larger vanilla model" (a tie) |
| 2610.06833 | Towards Looped Models Done Right II | B, strongest | Terminal K/V sharing works with sampled depth, fails with fixed depth; fixed-point lemma; code and checkpoints released | "Within 0.4 pt of the full cache" beyond the choice-task average |
| 2610.31633 | BeNice! | B | Fine-tune loss or LoRA makes final-pass sharing lossless vs a standard fine-tuning control, 3 seeds, exact sequential eval | "+8.35 Core" (includes extra training) |
| 2605.07721 | MELT | B | Same idea as ours: gated K/V refined across loops, converted from Ouro; parallel training fails | "Beats Qwen at equal memory" |
| 2607.15456 | Looped Latent Attention | B | Per-loop K/V is a low-rank trajectory; 4x codec | Generative numbers (100 to 200 item subsets, two GSM8K scores for one ratio) |
| 2610.07940 | Hybrid Latent Attention | B | Independent last-K/V failure on Ouro; two-pass training template; vLLM serving gains | Retention numbers as untuned (settings picked on reported benchmarks) |
| 2609.23033 | WaveFront Decoding | B | Huginn single-slot deepest K/V costs nothing (GSM8K 30.64 to 31.28); code released | |
| 2610.02383 | Shared Memory in Looped Transformers (LPT) | B | First-pass K/V plus window, exactly parallel, 4.7x less KV | Gains vs the un-normalized looped baseline |
| 2610.12582 | Elastic Latent Recurrence (Koi) | B, KV part only | Last-loop K/V at 4B+ and on agentic tasks | "Keeps most of the gain" (GDPval fails 52 vs 12 tasks, left out of the claim) |
| 2610.33360 | LSTM-Style Looped Transformers with Shared KV Caches | B, lowest weight | Measured train/serve gap and consistency-loss fix | Anything beyond 228M |
| 2610.34436 | RIPE caching | B, measurements only | Deep loops far more sensitive to prefix K/V; planes converge at 0.81 to 0.88 per loop | RIPE as a validated cache design |

### Precedents and the fast-weight view

| id | Paper | Tier | Use | Do not cite |
|---|---|---|---|---|
| 2405.10637 | Layer-Condensed KV Cache | A | Read-top-layer K/V with parallel sweep training; (w+1)/L memory | The 26x throughput as typical |
| 2002.09402 | Feedback Transformer | A | One memory per token read by all layers; state-tracking gains; training cost | Its LM/MT gains as compute-fair |
| 2502.07827 | Implicit Language Models are RNNs | A, borderline | Jacobi training, Gauss-Seidel serving, measured agreement | Efficiency (no compute-matched baseline) |
| 2202.05798 | The Dual Form of Neural Networks Revisited | A | K/V cache as a fast weight's training set (linear attention) | |
| 2102.11174 | Linear Transformers Are Secretly Fast Weight Programmers | A | Delta-rule fast-weight view of attention | |
| 2212.07677 | Transformers learn in-context by gradient descent | A | Attention layer as one GD step on a fast weight (toy linear regression) | |
| 2407.04620 | TTT layers | A | Per-token updates beat batch updates | Transformer comparison on its FLOP axis |
| 2505.23884 | LaCT | A | Per-token vs chunk updates for language | LM retrieval "consistently better" |
| 2502.10297 | DeltaProduct | A | Several inner steps per token, state tracking | LM gain as compute-matched |
| 2506.05233 | MesaNet | A | Per-token iterative solve, adaptive steps at inference | FLOP-matched superiority |
| 2412.06464 | Gated DeltaNet | A | Strong linear-RNN baseline | Gains over Mamba2 |
| 2501.12352 | Test-time regression | A, conceptual | Formalism with several GD iterations per token (toy experiments) | |
| 2202.05780 | Modern Self-Referential Weight Matrix | A | Self-modifying weights | Edge over DeltaNet |
| 2311.12424 | Looped Transformers are Better at Learning Learning Algorithms | A | Looping for ICL algorithms | Compute-fair comparison |
| 2310.17086 | Transformers Learn Higher-Order Optimization Methods for ICL | A | Layers act like Newton steps | |
| 2207.07061 | CALM | A | Early exit: re-projecting a past token's state works, copying K/V fails | |
| 2103.12803 | JFB | A | Last-iterate gradient as a descent direction | Accuracy vs Jacobian backprop |
| 2002.03629 | Parallel Nonlinear Equation Solving for Feedforward Computation | A | Jacobi / Gauss-Seidel exactness on triangular systems | Simulated speedups |
| 2511.07384 | Retrofitted Recurrence | A | Our base recipe | Headline at 32 test recurrences as inference-fair |

### Tier C (appendix only) and tier D (ignored)

| id | Paper | Tier | Reason |
|---|---|---|---|
| 2610.09013 | Enabling Dynamic Computation in Looped LMs | C | Near-lossless only at small savings; the measured 36% KV saving costs 3.7 to 4.7 pt; no throughput gain; shares authors with MELT |
| 2609.29812 | FlashLoop | C | Engine paper measured against its own engine; "lossless" overclaimed; undocumented last-step-reuse baseline |
| 2610.10381 | ResidualQuant | C | Correct but incremental quantization of every loop's K/V; does not bear on which K/V to read |
| 2609.01343 | SMELT | C | Scaling-law paper; not about K/V caching |
| 2501.00663 | Titans | C | The momentum and decay memory update may be credited; its numbers may not (figure-only long-context headline, a miscomputed baseline average, no code, a failed small reimplementation) |
| 2504.13173 | Miras | C | Reuses Titans' rows (same setup, acceptable) but takes 1.3B rows from Gated DeltaNet uncredited, and its ablations match no main-table row |
| 2609.37379 | Looped Transformers as Optimizers | C | All gains within single-seed noise (0.6 to 1.5 SE) |
| 2410.08292 | Can Looped Transformers Learn Multi-step GD for ICL? | C | Theory regime far from practice; thin experiments |
| 2512.24695 | Nested Learning / Hope | D, judgment call | States every model was retrained on a new mix, yet its TTT and Memora rows are Titans and Miras rows, including the miscomputed average |
| 2609.15160 | T-LoopFormer | D | Baseline table is a shifted copy of LoopFormer's under a different stated setup |
| 2610.28489 | Asymmetric Looped Transformers | D | At 135M to 1B the headline rests on a layerwise-LR trick given only to the method (at 60M a same-optimizer control exists and the gain survives) |

---

## Chapter 3 — Where The Idea Is Still Open

**No tier A or B paper trains near-exact Gauss-Seidel (per-token, last-K/V) recurrence in a looped LLM
at scale and evaluates reasoning, and none takes the fast-weight view of the refined K/V.** The closest
are MELT (chunk-wise, converted from Ouro), Kirsch (228M, loss only), HLA (latent cache, two-pass
training), LCKV and Implicit LMs (outside looped LLMs).

- Must-cite precedents: 2002.09402, 2405.10637, 2502.07827, 2002.03629, 2610.06833, 2610.31633,
  2605.07721, 2610.07940, 2510.24824.
- Risks the literature names for a parallel approximation of the sequential read: extra sweeps may not
  converge to sequential serving (Kirsch), and naive parallel training of a refined-K/V architecture
  can fail outright (MELT).
- For injected, random-depth models last-K/V sharing is already free zero-shot (Chapter 1), so a
  method trained in the Gauss-Seidel order must win on quality or on loop count at equal quality, not
  on memory, and must be compared against per_loop training plus zero-shot last-K/V.
- Untested: whether last-K/V recurrence trained in the Gauss-Seidel order improves state tracking or
  reasoning in a looped LLM, not only memory, and whether loop count can act as the number of inner
  steps on an explicit fast weight with per-token adaptive depth in training.
