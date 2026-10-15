# Idea Page: Mid-Training Loop Adaptation of a Pretrained Decoder

Owns the mid-training loop-adaptation research line: the problem statement,
the benchmark (recipe + metrics) and every known way the inherited RR recipe is
dirty, the val-loss vs downstream-accuracy decoupling, and the depth
distribution. Sibling idea page: [looped_nanogpt_per_site.md](looped_nanogpt_per_site.md)
(optimizer line, unrelated). Code lives in the `etd-rr-*` worktrees of
`qiaosungithub/nanoETD_adapt_loop` (`docs/RR_PORT.md`, `docs/RR_LOOPVAR.md`,
`docs/RR_EVAL.md` on those branches); results in the `RR TinyLlama-484` tab
([result-workbooks.md](../environment/result-workbooks.md#which-tab)).

## 1. Problem Statement

Take a pretrained pre-norm decoder, turn part of it into a weight-shared loop,
and mid-train it. **Hold the mid-training data (tokens and order) fixed and the
training FLOPs fixed**, then compare val loss, GSM8K and MATH. Steps:

1. Clean the recipe and the benchmark (section 3, section 4).
2. Explain why val loss does not rank methods the way GSM8K/MATH do (section 5).
3. Use a stationary (no-curriculum) distribution over the number of loops
   (section 6).
4. Propose a better loop-adaptation method and show it under the fixed-data,
   fixed-FLOPs protocol.

Scope: TinyLlama-1.1B-intermediate-step-1431k-3T first; 10B and 50B tokens of
Nemotron-CC-Math-v1 `4plus`.

**Fixed data and fixed FLOPs cannot both hold for the plain dense baseline**:
a loop spends more FLOPs per token, so at equal tokens the dense model has
fewer FLOPs, and at equal FLOPs the loop sees fewer tokens. The controls that
satisfy both constraints are the same-depth, extra-parameter arms (untied
copies of the core, or fresh layers): same tokens, same executed layers.
Report the dense baseline at both equal tokens and equal FLOPs (multi-epoch or
longer horizon) as context only.

## 2. The Base Model

TinyLlama 3T final checkpoint: Llama-2 architecture, 22 layers, width 2048,
32 query / 4 KV heads (GQA), SwiGLU 5632, RMSNorm 1e-5 pre-norm, RoPE theta
10000, untied embeddings, vocab 32000, pretraining context 2048, no biases. It
is a clean, standard pre-norm transformer. Things to keep in mind:

- It is weak on math at init. Mid-training on math text moves the dense val
  loss from 1.377 to 0.649, so most of what any arm learns is domain shift that
  the dense model also learns.
- It was pretrained with AdamW; the RR recipe switches body matrices to Muon
  (lr 1e-3) on a cooled-down checkpoint, so every arm starts with an optimizer
  and LR re-warm shock. That is identical across arms, but it confounds any
  claim about how fast a method "heals".
- The RR recipe trains at context 1024, half the pretraining context.

## 3. The RR Loop Adaptation, End To End

McLeish et al., *Retrofitted Recurrence* (arXiv 2511.07384), TinyLlama (4,8,4),
train recurrence 4:

1. **Surgery.** Prelude = layers 0-3, core = layers 10-17, coda = layers 18-21;
   layers 4-9 are deleted (704.7M body params, 72.7% of the parent).
2. **Adapter.** At the start of every core iteration,
   `x = W [s_{i-1}; e]` with `W` in R^{h x 2h}, `e` the prelude output.
   The released "untrained" init is far from the parent: its val loss at init
   is ~9.8 nats (dense parent 1.38).
3. **Latent init.** `s_0` is truncated-normal noise (std 0.0087, cut at 3 std),
   fresh per token, also at test time. Depth 1 is therefore not the parent model.
4. **Depth draw (Huginn).** Per draw group:
   `rate ~ LogNormal(log r - sigma^2/2, sigma = 0.5)`, `p = Poisson(rate) + 1`,
   `n = max(p - s, 0)` no-grad passes, then `k = min(s, p)` grad passes, with
   backprop window `s = min(r, 8)`. So `E[p] = r + 1`, not `r`. It is a
   Poisson-lognormal mixture (over-dispersed), not a pure Poisson.
5. **Curriculum.** `r(t) = max(1, ceil(r_max (1 - sqrt(1 - t / T_w))))`,
   `T_w = 0.75 T`. At `r_max = 4, T = 50k`: `r = 1` until update 16,407 (a third
   of training), 2 until 28,126, 3 until 35,157, then 4.
6. **Optimizer.** MuonWithAuxAdam: Muon lr 1e-3, wd 1e-4 (effectively none),
   momentum 0.95, NS5 in bf16, scale `max(1, rows/cols)^0.5`, on FUSED `Wqkv` and
   fused `[gate; up]`; AdamW lr 5e-5, betas (0.9, 0.95), eps effectively 1e-10,
   on embeddings, head, norms. HF warmup-stable-decay: warmup 125, cosine over
   the last 60% to 0.001x. Clip 1.0. bf16 autocast, fp32 master.
7. **Data.** 50k updates x 1024 rows x 1024 tokens = 52.4B tokens of
   Nemotron-CC-Math-v1 `4plus`, `[BOS] doc [EOS]` wrapped packing, no document
   masking, ~0.88 epoch. No healing phase in the math runs (the paper's
   two-phase FineWeb-Edu healing is only in its data-mixture section).
8. **FLOP rule.** `(6 N1 + 2 N2) D`, grad and no-grad params at the MEAN
   recurrence, embeddings excluded, attention ignored.
9. **Eval.** GSM8K `gsm8k_cot_sean` 1-shot flexible-extract, MATH `minerva_math`
   1-shot math_verify, greedy, 256 new tokens, context 768, batch 32, test
   recurrence R in {1, 2, 4, 8, 16, 32}.

## 4. Where The Recipe Is Dirty

Already handled in the port (`docs/RR_PORT.md` section 3): one seed for all
randomness, our own model with bitwise HF parity, atomic checkpoints, fixed-set
val loss, the first-update half batch (replicated), Adam eps 1e-10 and Muon
scale (replicated). What still matters for this line:

| # | Dirty point | Why it matters here |
|---|---|---|
| 1 | Surgery deletes 6 layers and the adapter starts random | RR measures prune + heal + loop at once. Use the full 22-layer model with an identity-preserving adapter (`[I | 0]` init) so the loop at init equals the parent |
| 2 | Random latent `s_0`, also at test time | Depth 1 is not the parent model; eval is stochastic (practically irrelevant for greedy, measured) |
| 3 | Depth draw is `1 + Poisson-lognormal`, `E[p] = r + 1`, truncated BPTT | "train recurrence 4" runs 5 passes on average; FLOP matching must use realized draws |
| 4 | One draw per 512-row group, shared by every rank | Depth is batch-level, not per sample: gradient noise from depth is correlated across the batch |
| 5 | Curriculum keeps `r = 1` for the first third | Interacts with the WSD schedule; an ablation of the distribution is confounded with the curriculum unless the curriculum is removed |
| 6 | Paper FLOP rule vs realized FLOPs differ by ~4% (rec4 50k: 3.78e20 paper vs 3.94e20 realized) | Pick one convention (realized) and use it for every arm |
| 7 | The paper's "equal FLOPs" comparison reads accuracy-vs-FLOPs off ONE token stream | At a given FLOP count the recurrent curve is a mid-run, un-cooled checkpoint, and the dense run ends at fewer FLOPs. Iso-FLOP claims need separate runs, each with its own full schedule |
| 8 | Muon sees fused `Wqkv` / `[gate; up]` in the raven model but separate q/k/v/o/gate/up/down in the dense baseline (upstream's own non-recurrent baseline also used separate matrices) | The optimizer geometry differs between arms. Unified on separate matrices: raven gets `rr.optimizer.muon_split_fused` (NS and scale per q/k/v and gate/up block). The full-model loop decoders already use the dense partition |
| 9 | Embeddings/head/norms at Adam 5e-5, matrices at Muon 1e-3, wd effectively 0 | New loop parameters (scalars, gates, adaLN) need their own lr; their lr choice changed results by several GSM8K points in the mod ablation |
| 10 | The raven remote code ignores the attention mask (left pads are attended, RoPE shifted); the decoder adapter masks pads | Raven-RR and loop/dense decoders are scored under different padding semantics; `<unk>` pads destroy raven outputs, EOS pads reproduce the paper |
| 11 | GSM8K 1-shot flexible-extract | Lenient: takes the last number. Strict-match differs a lot (RR rec4: 14.9 strict vs 36.8 flexible) |
| 12 | Single seed, binomial SE ~1.3 pt GSM8K (n = 1319), ~0.6 pt MATH (n = 5000) | A difference under ~3 pt GSM8K / ~1.5 pt MATH is noise without paired tests or more seeds |
| 13 | Val loss is our own fixed set (2048 held-out Nemotron rows); the paper reports none for the math runs | No paper reference to calibrate val loss against |
| 14 | Which depth to report for a random-depth model (mean r, E[p] = r + 1, or best R) | Must be fixed before seeing results |

## 5. Val Loss Does Not Rank Methods The Way GSM8K/MATH Do

**The paper does not contradict this, but it does not test it either.** Its
math-run figures plot only accuracy; val loss appears only for the Llama (2,4,2)
FineWeb experiments and the optimizer figure. The one explicit statement is
Appendix C.1 (Fig. 14): the additive adapter has higher training loss but about
the same accuracy as the linear one. Our TinyLlama reproduction matches the
paper's accuracies, so the paper's models implicitly show the same pattern:
RR rec4 has worse val loss than the dense parent and better GSM8K.

What our runs show (val at the trained depth / GSM8K / MATH):

| Comparison | Val loss | GSM8K | MATH |
|---|---|---|---|
| dense, 52B tokens | 0.649 | 30.1 | 24.0 |
| RR (4,8,4) rec4, 52B tokens, R = 4 | 0.679 | 36.8 | 26.9 |
| equal FLOPs (dense-50k FLOPs): ctl / rreye / etd loop k = 4 | 0.682 / 0.688 / 0.690 | 48.1 / 40.3 / 39.6 | 26.2 / 25.3 / 23.8 |
| equal data + equal executed layers (46): tied loops ctl / rreye / etd | 0.634 / 0.638 / 0.641 | 45.6 / 47.3 / 42.5 | 30.6 / 28.5 / 26.0 |
| same, untied copies / fresh layers A / B / C | 0.579 / 0.578 / 0.577 / 0.583 | 36.0 / 33.7 / 35.7 / 37.7 | 25.9 / 26.1 / 26.9 / 25.7 |
| same, untied copies WITH the RR `[h; p]` adapter | 0.579 | 46.9 | 29.1 |
| dense, 1.13 epochs (rec4-50k FLOPs) | 0.634 | 30.4 | 25.3 |
| dense weight soup of two seeds | 0.725 | 32.3 | 23.9 |

Reading:

- Across architectures, val loss tracks unique parameter count (untied/fresh
  ~0.578 vs tied ~0.636), while GSM8K tracks whether the core is re-entered with
  the input re-injected (tied loops and untied+adapter ~46-47 vs untied/fresh
  ~34-38). The untied+adapter arm gets both, which suggests the GSM8K gain comes
  from the per-pass injection, and the val gap from parameters.
- Within one architecture over training, val loss and accuracy still move
  together; the decoupling is between methods.
- Hypothesis to test, not established: val loss averages every token of math
  web text and is dominated by recall-heavy tokens that reward parameters;
  GSM8K/MATH reward multi-step computation per answer token. Check by splitting
  val loss into token classes (numbers / operators / prose) and by scoring the
  GSM8K/MATH gold answers' log-likelihood.

## 6. The Depth Distribution

The current random-depth code is the Huginn draw of section 3, step 4. Two
configurations exist:

- `rand<r>`: RR 1-sqrt curriculum to mean `r` over the first 75%.
- `fixdist<r>`: the same draw with the curriculum removed (`r` constant from
  update 0, `s = r`). `fixdist4` realizes 0.99x the FLOPs of fixed `k = 4`.

So "Poisson" today means `1 + Poisson(LogNormal)` with sigma 0.5, batch-level
draws and a truncated backprop window. A pure Poisson is sigma = 0. Decide
explicitly: the +1 shift (or `p >= 1` truncation), sigma, the backprop window,
draw granularity (per sample vs per batch group), and the eval depth.

Known results: with the curriculum to mean 7, the RR-adapter loop on TinyLlama
ended flat across depth and no better than dense (GSM8K ~28-29 vs fixed-k4
47.3), while a projector loop on OLMo with the same draw beat both dense and RR.
TinyLlama ctl ablations at the 10k budget (fixed k = 1..4, `rand1/3/5/7`,
`fixdist2/3/4`) and 50k `fixdist4` / `rand7` runs for ctl, rreye and adaLN
exist; their results are not in the results tab yet.

## 7. Ablation Backlog

Every item is run under the section-1 protocol: same data, realized FLOPs
matched, full schedule per arm, final checkpoint only.

| # | Ablation | Current value | What the paper did |
|---|---|---|---|
| A1 | Muon lr | 1e-3 | One value, no sweep reported (App. D) |
| A2 | AdamW lr (embeddings, head, norms) | 5e-5 | One value, no sweep reported |
| A3 | Warmup length | 125 updates (0.25%), linear from 0.001x | "adjusted per experiment", no ablation |
| A4 | Schedule shape | WSD, cosine over the last 60% to 0.001x, one factor for both groups | No ablation |
| A5 | Which layers form prelude / core / coda | full model 0-9 / 10-17 / 18-21 (ours); RR (4,8,4) = 0-3 / 10-17 / 18-21 | Small search on Llama-1B by FineWeb-Edu train loss (Fig. 12), ShortGPT comparison (Fig. 13) |
| A6 | Delete layers or keep all | keep all (ours); RR deletes 4-9 | Deleting is motivated only by FLOPs per recurrence; (6,10,6) keeping all scores higher at more FLOPs (Fig. 14), (7,8,7) gains little (Fig. 15). Never compared at equal FLOPs |
| A7 | Truncated BPTT window | `s = min(r, 8)` grad passes, the rest no-grad (8 is the config cap `mean_backprop_depth`, inactive for r <= 8, so fixdist r truncates at r). Pure-Poisson runs: window `2 x mean` (operator decision 2026-10-14) | Inherited from Huginn; only "schedule the max backprop depth" is ablated (Fig. 18) |
| A8 | Depth shared by the batch or per sample | one draw per 512-row group, shared by all ranks | Not ablated (a side effect of seeding by the micro-batch counter) |
| A9 | Depth distribution | `1 + Poisson-lognormal` (sigma 0.5) and fixed k; target: the simplest Poisson, no curriculum. Running at 10k (CtL, branch `rr-loop-poisson`): fixdist5 299799793, fixdist6 299800698 (fixdist2-4 done); poisson m = 2..6 with `p = 1 + Poisson(m - 1)` (E[p] = m, realized FLOPs = fixed k = m within 0.5%), window 2m: 299818015 / 299818036 / 299817849 / 299818276 / poisson6 queued on b200-8 | Poisson-lognormal only |
| A10 | pass@k / maj@k vs loops at matched inference FLOPs; do loops stack with pass@k | greedy only, never measured | Not measured |
| A11 | Muon on fused vs separate matrices | Hard-coded to separate row blocks in the raven optimizer, no config key (branch `rr-muon-split` @89e224f, not merged yet). Every RR result before it used the fused geometry. Loop decoders were always separate | Fused in the recurrent model, separate in the dense baseline |
| A12 | Loop state update: residual vs LSTM-style gating | Residual: each core pass adds its update to the stream, `h_t = core(z_t)`. Candidate (operator, 2026-10-15): LSTM gates on the cross-pass update (forget / input / output gates from `[h_{t-1}; p]`), initialised to reproduce the current variant exactly | Not considered |

## 8. Open Questions

- Which loop arm is the reference method: ctl (best GSM8K at equal FLOPs), or
  rreye (`[I | 0]` adapter, best at equal data)?
- Does the val/accuracy decoupling survive a token-class split of val loss?
- Does a stationary distribution beat fixed `k` at equal realized FLOPs, and
  does it buy depth extrapolation (R > trained depth)?
