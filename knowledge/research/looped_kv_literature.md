# Screened Literature: Looping As Per-Token K/V Or Fast-Weight Refinement

Owns the screened paper list for one idea: in a weight-shared (looped) decoder, a loop pass refines
the current token's K/V, later tokens read only the final K/V of earlier tokens (per-token recurrence),
and this generalizes to looping as a fast-weight update (the test-time-training view). Standard looping,
where pass t reads the pass-t K/V of every token, is a Jacobi iteration over (token, pass); last-K/V
per-token recurrence is the Gauss-Seidel order. The experiments live on
[midtrain_loop_adaptation.md](midtrain_loop_adaptation.md). How papers were screened, and the rule that
only kept papers count: [literature-review skill](../../harness/skills/literature-review/SKILL.md).
The full per-paper audits (claim, C1 to C10 with table references) are in
`~/work/lit-review/looped_kv_fastweight/G{1..5}_*.md`; the independent re-check of every DISCARD's
decisive numbers is `DISCARD_VERIFY.md` in the same directory.

Chapter 1 is what the kept papers establish; Chapter 2 is the kept list; Chapter 3 is the ignored
list; Chapter 4 is where the idea is still open.

---

## Chapter 1 — What The Kept Papers Establish

**Reading only the last loop's K/V works zero-shot only for models whose loop contracts; models
trained at fixed depth with a terminal loss break.** Models trained with random depth, truncated
backprop or damped/gated updates tolerate it (2610.06833, 2610.31633, 2610.12582, 2610.34436 on
Raven/Huginn); the K/V planes approach the last one geometrically, at about 0.81 to 0.88 per loop
(2610.34436). Zero-shot last-K/V on Ouro checkpoints fails badly in independent re-tests (2610.07940:
MATH500 75.9 to 45.9; 2605.07721 and 2610.09013 agree, but those two share authors). This matches the
fixed-depth vs random-depth split on the idea page.

**The Jacobi and Gauss-Seidel orders reach the same fixed point when the loop contracts, and that is
proven.** 2610.06833 Lemma 1 shows parallel joint iteration and frozen-prefix token-by-token decoding
converge to one fixed point; 2002.03629 gives the exact Jacobi-on-a-triangular-system statement
(convergence in at most T sweeps).

**Training in parallel and serving sequentially leaves a gap that must be measured; extra parallel
sweeps do not close it on their own.** 2610.33360 measures about 0.05 nats and removes 81 to 89% of it
with a K/V consistency loss late in training, and finds loss is lowest at the trained sweep count, not
at more sweeps. 2502.07827 trains Jacobi and serves Gauss-Seidel with 97.6 to 97.7% greedy agreement, at
2 to 4x training cost and about 50 to 70 iterations. 2405.10637 (LCKV) trains a read-the-top-layer-K/V
dependency with 7 no-grad sweeps plus 2 grad sweeps (about 3x training time). 2610.07940 Appendix E is a
two-pass training recipe of the same family.

**Reading earlier tokens' most-processed state buys state tracking that standard transformers lack, at
a training-time cost.** 2002.09402 (Feedback Transformer): random walk 68 to 100, code execution 33.7 to
99.1, at 2.2 to 3.5x training time; top-layer-only memory works as well as all layers.

**Several sequential inner steps per token on a fast weight increase expressivity.** 2502.10297
(DeltaProduct) takes n_h delta-rule steps per token and gains state tracking; adaptive n_h is future
work. 2506.05233 (MesaNet) solves each token's regression with conjugate gradient, fixed 30 steps in
training, adaptive at inference (about 9 steps on average at tolerance 1e-4); its iterations refine the
read only, not what later tokens see. In TTT, smaller inner mini-batches (closer to per-token
Gauss-Seidel) are better (2407.04620 Fig 7: 14.05 to 12.35 perplexity from b = 2048 to 16), and LaCT
finds per-token updates beat large chunks for language at matched state size (2505.23884 Fig 8b).

**A gradient-trained linear layer is exactly attention over its training pairs,** so a K/V cache is
the training set of a fast weight (2202.05798, 2102.11174); a trained linear self-attention layer does
one GD step on such a fast weight (2212.07677).

---

## Chapter 2 — Kept Papers

**Cite these, each with its caveat in the same sentence; never cite the listed weak claims.**

| id | Paper | Verdict | Use | Do not cite |
|---|---|---|---|---|
| 2609.23033 | WaveFront Decoding | KEEP | Cross-depth K/V sharing reads the latest-written K/V; acceptance 0.88 to 0.97 | |
| 2102.11174 | Linear Transformers Are Secretly Fast Weight Programmers | KEEP | Fast-weight / delta-rule view of attention | |
| 2202.05798 | The Dual Form of Neural Networks Revisited | KEEP | GD-trained layer = attention over training pairs | |
| 2610.33360 | LSTM-Style Looped Transformers with Shared KV Caches | KEEP-CAVEAT 3 | Measured Jacobi/Gauss-Seidel train-serve gap, consistency loss; small scale, loss only | |
| 2610.06833 | Towards Looped Models Done Right II | KEEP-CAVEAT 3 | Fixed-point lemma, terminal K/V sharing, fixed depth breaks sharing | Learned-prior and orthogonal-injection gains (single seed, small) |
| 2002.09402 | Feedback Transformer | KEEP-CAVEAT 3 | State-tracking gains from reading past top-layer state; training cost | Its LM/MT gains as compute-fair |
| 2405.10637 | Layer-Condensed KV Cache | KEEP-CAVEAT 3 | Jacobi-sweep training exact in the limit | The 26x throughput as typical |
| 2502.10297 | DeltaProduct | KEEP-CAVEAT 3 | Multiple inner steps per token, state tracking | LM gain as compute-matched |
| 2506.05233 | MesaNet | KEEP-CAVEAT 3 | Per-token iterative solve, adaptive steps at inference | FLOP-matched superiority |
| 2412.06464 | Gated DeltaNet | KEEP-CAVEAT 3 | Strong linear-RNN baseline | Gains over Mamba2 (small, shared LR) |
| 2212.07677 | Transformers learn in-context by gradient descent | KEEP-CAVEAT 3 | Attention layer = GD step on a fast weight; toy linear regression only | |
| 2610.31633 | BeNice! | KEEP-CAVEAT 2 | Stochastic depth makes K/V shareable; final-K/V broadcast fine-tune | The "+8.35 Core" (includes extra training) |
| 2610.12582 | Elastic Latent Recurrence | KEEP-CAVEAT 2 | One-loop parity; last-loop K/V at inference | "Last-loop K/V keeps most of the gain" (fails on GDPval, omitted from the claim) |
| 2610.34436 | RIPE caching | KEEP-CAVEAT 2 | Deepest-plane reads near-lossless on Raven; geometric convergence of planes | Tail statistics (4 prompts) |
| 2610.02383 | Shared Memory in Looped Transformers (LPT) | KEEP-CAVEAT 2 | First-pass K/V sharing; its best-normalized looped baseline | Gains vs the un-normalized baseline |
| 2510.24824 | Parallel Loop Transformer | KEEP-CAVEAT 2 | First-loop K/V + gated sliding window at MoE scale | "Beats a larger vanilla model" (a tie) |
| 2610.07940 | Hybrid Latent Attention for Looped LMs | KEEP-CAVEAT 2 | Independent re-test of last-K/V on Ouro; two-pass training recipe | Retention numbers as untuned (hyperparameters picked on reported benchmarks) |
| 2610.10381 | ResidualQuant | KEEP-CAVEAT 2 | K/V across loops highly similar; final-loop K/V as reference | Ablation deltas (within noise) |
| 2609.29812 | FlashLoop | KEEP-CAVEAT 2 | Cross-loop redundancy; independent last-loop re-test (about 1.3 to 2 pt cost) | "Lossless" |
| 2507.10524 | Mixture-of-Recursions | KEEP-CAVEAT 2 | Per-token depth with recursion-wise or first-recursion K/V | "Significantly lower perplexity at equal FLOPs" (contradicted by its Tables 7 and 9) |
| 2502.05171 | Huginn | KEEP-CAVEAT 2 | Released recurrent-depth model; slot K/V sharing (i mod k) | KV-sharing parity (MT-Bench only, underpowered) |
| 2511.07384 | Retrofitted Recurrence | KEEP-CAVEAT 2 | Our base recipe; training-FLOP-matched math gains | Headline at 32 test recurrences as inference-fair |
| 2407.04620 | TTT layers | KEEP-CAVEAT 2 | Inner mini-batch size: per-token beats batch | Transformer comparison on its FLOP axis |
| 2505.23884 | LaCT | KEEP-CAVEAT 2 | Per-token vs chunk updates for language | LM retrieval "consistently better" (appendix tables disagree) |
| 2501.12352 | Test-time regression | KEEP-CAVEAT 2 | Formalism with I GD iterations per token; toy experiments only | |
| 2202.05780 | Modern Self-Referential Weight Matrix | KEEP-CAVEAT 2 | Self-modifying weights | Edge over DeltaNet (within 1 std) |
| 2002.03629 | Parallel Nonlinear Equation Solving for Feedforward Computation | KEEP-CAVEAT 2 | Jacobi / Gauss-Seidel vocabulary and exactness | DenseNet / PixelCNN++ speedups (simulated or oracle-stopped) |
| 2502.07827 | Implicit Language Models are RNNs | KEEP-CAVEAT 2 | Closest prior: Jacobi training, Gauss-Seidel serving | Efficiency (no compute-matched baseline) |
| 2207.07061 | CALM | KEEP-CAVEAT 2 | Early-exit: re-projecting a past token's state works, copying K/V fails | |
| 2103.12803 | JFB (Jacobian-free backprop) | KEEP-CAVEAT 2 | Last-iterate gradient as a descent direction | Accuracy vs Jacobian backprop (confounded) |
| 2311.12424 | Looped Transformers are Better at Learning Learning Algorithms | KEEP-CAVEAT 2 | Looping for ICL algorithms | Compute-fair comparison (20 to 70 loops vs 12 layers) |
| 2310.17086 | Transformers Learn Higher-Order Optimization Methods for ICL | KEEP-CAVEAT 2 | Layers act like iterative Newton steps | |
| 2605.07721 | MELT | KEEP-CAVEAT 1 | Same idea: one gated K/V per layer shared across loops, chunk-wise training | "Beats Qwen at equal memory" |
| 2610.09013 | Enabling Dynamic Computation in Looped LMs | KEEP-CAVEAT 1 | Best-available K/V for per-token depth | The 30% saving as realized speed (no throughput gain) |
| 2410.08292 | Can Looped Transformers Learn Multi-step GD for ICL? | KEEP-CAVEAT 1 | Theory only, regime far from practice | Any empirical claim |

---

## Chapter 3 — Ignored Papers

**These papers failed screening; ignore them completely, even where the idea overlaps ours.**

| id | Paper | Why it was discarded |
|---|---|---|
| 2510.25741 | Ouro | "Matches up to 12B models" rests on in-house baselines far below their published numbers (Qwen3-4B GSM8K 72.86 vs 87.79, partly a 3-shot vs 4-shot protocol difference), an implausible cell (Gemma3-1B MATH500 41.0 with GSM8K 2.05), and the same baselines differing between its Tables 7 and 8; its own same-data FLOP-matched test favors standard models. Its released checkpoints remain usable as artifacts |
| 2501.00663 | Titans | The over-2M-context headline exists only in a figure with an unstated protocol; a baseline average is miscomputed; no code, and an independent reimplementation did not reproduce it |
| 2504.13173 | Miras (It's All Connected) | Baseline rows copied unchanged from other papers; its ablation numbers match no main-table row; no code |
| 2512.24695 | Nested Learning / Hope | Claims every model was retrained on a new mix, yet baseline rows are copied from Titans and Miras, including the miscomputed average; no code |
| 2609.15160 | T-LoopFormer | Baseline table is a shifted copy of LoopFormer's despite a different stated setup; uncited Mixture-of-Recursions mechanisms; gains within noise |
| 2610.28489 | Asymmetric Looped Transformers | A layerwise-LR method given only to the method is worth about as much as the reported gains at 135M to 1B, where no same-optimizer control exists; the 1B gap is 0.05 perplexity, single seed. Only at 60M does a same-optimizer comparison exist, and there the architecture gain survives |
| 2609.37379 | Looped Transformers as Optimizers | All gains (+1.0 to +1.7 EM, alignment gains +0.15 / +0.54) are 0.6 to 1.5 binomial SE, single seed; the 5B gain is mostly MMLU. Its aggregate counts GSM8K and HumanEval twice, which adds noise but does not inflate the gain (borderline; multi-seed evidence would reopen it) |

---

## Chapter 4 — Where The Idea Is Still Open

**No kept paper trains exact or near-exact Gauss-Seidel (per-token, last-K/V) recurrence in a looped
LLM at scale, and none takes the fast-weight view of the refined K/V.** The closest are MELT (gated
shared K/V, chunk-wise distillation from a Jacobi-trained model), 2610.33360 (small scale, consistency
loss) and 2502.07827 (implicit fixed-point models, not looped LLMs with K/V reads).

- Must-cite precedents for this idea: 2002.09402, 2405.10637, 2502.07827, 2002.03629, 2610.33360,
  2610.06833, 2605.07721.
- Untested: whether last-K/V recurrence trained in the Gauss-Seidel order improves state tracking or
  reasoning in a looped LLM (not only memory), and whether the loop count can act as the number of
  inner steps on an explicit fast weight with per-token adaptive depth in training.
