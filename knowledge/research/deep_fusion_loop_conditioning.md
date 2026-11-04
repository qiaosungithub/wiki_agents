# Idea Page: Deep Fusion Of The Loop State

Owns the deep-fusion framing of loop adaptation: why every inherited way of
feeding a looped block (RR, CtL, Parcae diagonal, ETD, LSTM gates) is early
fusion, what deep fusion means for a loop, which of our arms are which, what
our runs show so far, and the plan for showing indirectly that deep fusion is
the better design. The benchmark, recipe and protocol are on the sibling page
[midtrain_loop_adaptation.md](midtrain_loop_adaptation.md) (section 6 is the
default protocol v2); results live in the `RR TinyLlama-484` tab
([result-workbooks.md](../environment/result-workbooks.md#which-tab)); code is
`qiaosungithub/nanoETD_adapt_loop` (`models/loop_decoder.py` `inject` /
`run_steps`, `models/loop_ops.py` `_adaln_layer`).

Chapter 1 is the claim; Chapter 2 is the in-house evidence and its confounds;
Chapter 3 is the plan for side evidence; Chapter 4 is what the screened literature says.

---

## Chapter 1 — The Claim

### Loop adaptation is a fusion problem

**Every looped block computes `h_t = f(e, h_{t-1})` from two signals, the
prelude output `e` (fixed across passes) and the previous pass output
`h_{t-1}`, so a loop-adaptation method is a choice of how to fuse two inputs.**
`f` is the core block, `L` pretrained layers `F_L o ... o F_1` (L = 8 in
7 + 8 + 7). The two signals play different roles: `e` is the problem, `h_{t-1}`
is the model's current guess, which the operator reads as a prior (each pass
enters the core already holding the previous pass's prediction).

### Early fusion: mix once, then run the unmodified layers

**All the inherited methods mix `e` and `h_{t-1}` once, at the input of the
core, and then run the original layers unchanged:
`z_t = g(e, h_{t-1})`, `h_t = F_L(... F_1(z_t))`.** This is early fusion in the
VLM sense: like a LLaVA-style projector or a soft prompt, the mixing operator
only ever touches the input space of layer 1.

| Method | `g(e, h_{t-1})` | Extra parameters |
|---|---|---|
| ETD (no injection) | `h_{t-1}` | 0 |
| CtL | `w e + (1 - w) h_{t-1}`, `w = sigmoid(a)` | 1 scalar |
| RR | `A [h_{t-1}; e]`, `A` in R^{h x 2h} | 8.4M |
| Parcae diagonal | `decay * h_{t-1} + g * (B e)`, per channel | per-channel vectors (+ dense `B`) |
| LSTM-style gates | gated mix of `e` and the carried cell, gates from `[h_{t-1}; e]` | one `2h -> 3h` map |
| MLP projector | `P(h_{t-1})`, no `e` | 2-layer MLP |

### Deep fusion: one signal on the residual, the other re-injected into every layer

**Deep fusion keeps one signal on the residual stream and treats the other as a
condition that every core layer reads again: `x_j = F_j(x_{j-1}; c)`,
`j = 1..L`.** With `c` derived from `h_{t-1}`, the prior is available at full
strength in every layer instead of being one summand of layer 1's input. Every
deep arm we have is zero-initialized so that the model at update 0 is exactly
the pretrained model at every depth.

| Arm (config) | Residual | Condition and how each layer reads it |
|---|---|---|
| adaLN (`loop.variant adaln`) | `e` | `c = SiLU(rms_norm(h_{t-1}))`; per-layer zero-init Linear gives scale / shift / gate on both pre-norms (DiT adaLN-Zero) |
| adaLN swap (`loop.adaln_residual hidden`) | `h_{t-1}` | `c = SiLU(rms_norm(e))`, the roles of the two signals exchanged |
| adaLN + conditioning block (`loop.adaln_cond_block per_layer`) | `e` | `h_{t-1}` first passes through a per-layer copy of a pretrained layer (it can mix tokens), then adaLN |
| cross-attention (`loop.prior xattn`) | `e` | each layer cross-attends causally to `rms_norm(h_{t-1})`, zero-init output |
| two streams (`loop.prior twostream`) | `e` | a second copy of the core runs on `h_{t-1}` (restarted, `2s-h`) or its own carried state (`2s-b`); MMDiT-like joint attention, zero-init gate |
| previous-pass K/V (`loop.prior prevkv`) | `e` | each layer also attends to its own previous-pass keys / values |
| layermix (`loop.variant layermix`) | `e` | `x <- x + alpha_j W_j rms_norm(h_{t-1})` at every layer, `alpha_j = 0` at init |
| pass-axis attention (`loop.prior passattn`) | `e` | after each layer a token attends over its own earlier pass outputs |

### Why deep fusion should help: four hypotheses

**The hypotheses differ in what they predict for an additive per-layer
injection, which is how our runs can tell them apart.**

| # | Hypothesis | Prediction |
|---|---|---|
| H1 | Dilution: in a pre-norm residual stream the input mix is one summand that later layers' writes progressively dominate, so the prior fades with depth; a re-read condition stays fresh | Any per-layer injection, including additive layermix, beats early fusion |
| H2 | Access form: modulation (scale / gate) and attention let the condition change how a layer processes its input, not only what it adds; an early mix can only shift the input | Only non-additive per-layer paths (adaLN, cross-attention, joint attention) beat early fusion; layermix ≈ early fusion, because an additive write at layer j reaches every later layer through the residual anyway |
| H3 | Role separation: the residual carries the problem, the condition carries the current guess | Deep-fusing `h_{t-1}` (adaLN) beats deep-fusing `e` (swap) |
| H4 | Preservation: zero-init per-layer conditioning leaves the pretrained computation intact and lets each layer choose how much of the prior to use | Deep fusion keeps more of the loop gain when the core is frozen, and forgets less off-domain |

---

## Chapter 2 — In-House Evidence

### Protocol v2 results by fusion type

**Under protocol v2, adaLN beats every early-fusion arm at every depth cap on
GSM8K, and the two arms that give the condition its own transformer path (the
conditioning block and two streams) beat it again; additive per-layer injection
does not beat early fusion.** GSM8K flex / MATH at `k = R`, 7 + 8 + 7, 10k
updates, seed 74 unless marked. Single-seed GSM8K differences under ~3 points
are noise ([midtrain_loop_adaptation.md §4](midtrain_loop_adaptation.md#4-where-the-recipe-is-dirty), item 12).

| Arm | Fusion | R = 4 | R = 8 | R = 16 | R = 32 |
|---|---|---|---|---|---|
| CtL [3 seed] | early | 42.2 / 26.2 | 44.1 / 27.8 | 47.1 / 28.6 | 46.6 / 29.0 |
| RR-2 (RR mix on 7 + 8 + 7) | early | 42.7 / 26.6 | 45.0 / 26.7 | 46.6 / 28.1 | 46.0 / 28.4 |
| Parcae diagonal, dense B | early | 41.4 / 26.3 | 45.0 / 28.7 | 44.4 / 29.4 | 46.9 / 29.2 |
| layermix | deep, additive | 41.5 / 27.0 | 42.5 / 27.7 | 43.7 / 27.8 | — |
| adaLN [3 seed; R = 32: 2 seed] | deep, modulation | 43.4 / 26.9 | 47.6 / 29.4 | 49.0 / 29.6 | 49.2 / 29.0 |
| adaLN swap (`e` as condition) | deep, modulation | 40.6 / 23.6 | 45.9 / 28.0 | 46.9 / 28.9 | 49.1 / 29.6 |
| cross-attention, no adaLN | deep, attention | 42.2 / 26.9 | 46.4 / 27.4 | — | — |
| adaLN + conditioning block | deep, own layer | 46.9 / 28.7 | 50.5 / 29.3 | — | — |
| two streams, restarted (`2s-h`) | deep, joint attention | 48.6 / 28.2 | 50.7 / 29.4 | — | — |
| two streams, carried (`2s-b`) | deep, joint attention | — | 52.3 / 30.6 | — | — |

Reading:

- adaLN minus CtL (3-seed means): +1.2 / +3.6 / +1.8 / +2.6 GSM8K and
  +0.7 / +1.6 / +1.0 / 0.0 MATH. The sign is the same at all four caps, but
  only R = 8 clears about 3 standard errors of the difference of means
  (R = 4 / 16 / 32: about 1.5 / 1.2 / 2.1).
- layermix ≈ CtL at every cap, and cross-attention without adaLN ≈ CtL at
  R = 4. This favors H2 over H1: re-injecting at every layer is not enough by
  itself; the condition has to enter through a non-additive path.
- **layermix ties CtL because it trains itself into early fusion, not because
  its gates stay shut.** Its logged per-layer gains (`train/loop/layermix_gain_<j>`,
  the rms of `alpha_j W_j c` per unit-rms `c`) settle at about 0.20 / 0.08 /
  0.06 / 0.08 / 0.06 for core layers 1-5 and under 0.005 for layers 6-8, with
  the same shape at R = 4 / 8 / 16. Against the pretrained residual rms at those
  layers (0.054 at the first core layer, 0.08-0.11 at layers 2-5) the first
  layer's add is about 4x the residual, so `h_{t-1}` dominates the core input,
  and the last three layers add nothing because the residual already carries
  the earlier adds. Two caveats: the reference scale is the pretrained model's,
  not the trained checkpoint's, and the gain assumes an isotropic `c`. Gates
  that sit at zero under Muon may also be stuck rather than unwanted. For
  comparison, CtL learns `w` ≈ 0.83, so `h_{t-1}` carries roughly 30% of its
  core input's energy at the pretrained scale.
- adaLN beats its swap at R = 4 (MATH 26.9 vs 23.6) and R = 8, and they tie at
  R = 32: weak support for H3.
- Previous-pass K/V without adaLN collapses to the no-loop model (GSM8K ~25 at
  every k), and pass-axis attention is below CtL: not every deep path works.

### Confounds that block the claim today

**The largest deep-fusion gains come from the arms with the most added
parameters and compute, so the table does not yet separate "deep" from
"bigger".**

| Confound | Size | What removes it |
|---|---|---|
| Parameters | adaLN +201M, two streams about +350M (a second copy of the 8 core layers), conditioning block about +550M (8 extra layers on top of adaLN), layermix +34M, CtL 1 scalar | A capacity-matched early-fusion arm (§3, E2). Weak prior evidence: untied early-fusion copies add 1.06B parameters and do not raise GSM8K ([midtrain_loop_adaptation.md §5](midtrain_loop_adaptation.md#5-val-loss-does-not-rank-methods-the-way-gsm8kmath-do)) |
| Compute | the conditioning block and two streams run about one extra core-sized path per pass | Report against training and inference FLOPs; FLOP-matched depth for the early arm |
| Seeds | only CtL and adaLN have 3 seeds | 3 seeds for the R = 8 deep arms |
| Optimizer | new per-layer parameters have their own learning rate | The lr of the fusion parameters swept for both families |

---

## Chapter 3 — Plan For Side Evidence

**The goal is evidence that deep fusion is better for a reason, not only a
higher number: a dose-response in injection depth, a capacity-matched control,
and probes showing that early fusion's prior fades with depth while deep
fusion's does not.** Ordered by cost; E3-E5 are eval-only on existing
checkpoints.

| # | Experiment | Question | Prediction if deep fusion is the cause |
|---|---|---|---|
| E1 | Injection-depth dose-response: adaLN on only the first m of the 8 core layers, m in {1, 2, 4, 8}, plus a last-m control; per-layer Linears zeroed and frozen elsewhere | Does the gain grow with the number of layers that read the prior? m = 1 is early fusion through the same operator | Monotone in m; last-m beats first-m at equal m if the prior fades (the VPT-deep / P-tuning v2 / DeepStack style of argument) |
| E2 | Capacity-matched early fusion: (a) the conditioning block applied once at the core input, `z_t = e + Block(rms_norm(h_{t-1}))`, zero-init output; (b) adaLN with one Linear shared by all 8 layers (25M) vs per-layer (201M); (c) two streams whose second stream feeds only the core input | Is the gain from depth of fusion or from parameters? | Deep beats its early twin at equal parameters and FLOPs; shared-Linear adaLN keeps most of adaLN's gain |
| E3 | Prior-persistence probe: for each core layer j, the influence of `h_{t-1}` on `x_j` (relative change of `x_j` when `h_{t-1}` is replaced by another pass's state), the Jacobian norm, and a linear probe decoding `h_{t-1} - e` from `x_j` | Does the prior fade with depth in early fusion? | Influence decays with j for CtL / RR-2 / diagonal, stays flat for adaLN / conditioning block |
| E4 | Gate usage: per-layer and per-pass magnitude of the adaLN scale / shift / gate, layermix `alpha_j`, cross-attention and two-stream gates | Does the trained model use the prior in deep layers? | Deep layers carry modulation comparable to layer 1 (the Flamingo per-layer gate analysis) |
| E5 | Prior quality test: one pass with the prior replaced by (a) an oracle, the state at `k = 2R`, (b) a corrupted prior (another sequence, shuffled positions, zero) | How efficiently does each architecture turn a prior into loss, and how much does it rely on it? | Larger loss drop from the oracle and larger loss rise from corruption for deep fusion |
| E6 | Frozen core: train only the fusion parameters (core, prelude and coda frozen) | Early fusion becomes an input adapter (prompt-tuning-like), deep fusion per-layer adapters (VPT-deep / LoRA-like); also measures forgetting (H4) | Deep fusion keeps much more of the loop gain; less off-domain loss increase at k = 1 |
| E7 | Synthetic iterated-computation tasks from scratch (k-hop pointer chasing, multi-digit addition, graph reachability), small looped transformers, many seeds, early vs deep at matched parameters | Does the effect survive without a pretrained model and without GSM8K noise? | Deep fusion learns faster and extrapolates further in depth |
| E8 | Gradient path: `||dL/dh_t||` across passes for early vs deep, and last-pass-only truncated backprop for CtL (adaLN already has it) | Does deep fusion shorten the gradient path through the loop? | Slower decay across passes for deep fusion; smaller loss from truncation |

---

## Chapter 4 — What The Literature Says

**Screened review (59 papers read in full, 41 tier A, 7 B, 11 C, none
discarded): deep fusion beats early fusion by a wide margin only when the host
network is frozen; with a trained host, which is our case, the gain comes from
how the condition enters a layer (modulation or attention, plus zero-init), not
from re-injecting it at every layer.** Full review, per-paper audits and the
verification log: `~/work/lit-review/deep_fusion/SUMMARY.md`. Almost every
comparison below is a single seed, and most deep arms carry extra parameters.

| Hypothesis | Literature verdict | Strongest kept evidence |
|---|---|---|
| H1 dilution | Holds only for frozen or small hosts, and shrinks with scale | Deep vs shallow prompts: VPT, prefix-tuning, eP-ALM; P-tuning v2 gap +15 to +24 points near 350M, +1.2 at 10B |
| H2 access form | Best supported | Additive per-layer re-injection ties a single injection in six settings (DeepStack dummy, BERT-fused additive, ResFormer hidden residual, VPT add, LaVi shift-only, U-ViT skips); modulation or attention at the same sites wins (ADM AdaGN vs addition, FiLM scale term, ResFormer value path, BERT-fused attention, DiT adaLN-Zero) |
| H3 role separation | Weak once parameters are matched | Positive results all carry about 2x parameters (MoT, MMDiT, LMFusion, CogVLM); Bugliarello (10 seeds) finds single- and two-stream equal on 4 of 5 tasks; DiT-Air ties MMDiT with 66% fewer parameters |
| H4 preservation | Zero-init is the most consistently measured ingredient; forgetting results are mixed | Flamingo tanh gate (-4.2 without it), LLaMA-Adapter zero vs random init, DiT adaLN-Zero vs adaLN; NVLM's token arm keeps text better than cross-attention, LaVi's modulation keeps it best |

What proponents argue vs what they measured:

- CogVLM's "shallow alignment is like p-tuning, deep fusion like LoRA" is argued
  only; its own Table 4 shows input tokens plus an unfrozen LLM recover most of
  the visual expert's gain.
- "Cross-attention keeps text ability" (Llama 3 vision, NVLM-X) comes from
  freezing the LM, not from cross-attention.
- "Every layer" is rarely the best placement: RETRO and MBT score worst with
  all-layer fusion, FiLM in block 1 only matches all blocks, StyleGAN's input
  latent with the same mapping network matches per-layer styles. Sparse,
  spread-out injection wins most placement sweeps; shallow-only also loses.
- Efficiency on long visual sequences, a main VLM argument for cross-attention,
  does not apply: `h_{t-1}` is as long as the sequence.

**VLM early fusion is not our early fusion, which makes one baseline
missing.** A VLM's early fusion gives the condition its own token positions,
which every layer re-reads through attention; ours mixes vectors into the same
positions. So the VLM counterexamples (NVLM, Idefics2, mPLUG-Owl3, DiT-Air) say
per-layer cross-attention is unnecessary when the condition has its own tokens,
not that CtL is enough. The matching arm, `h_{t-1}` appended as extra tokens
that the core attends to, was dropped from the cond study for doubling the
sequence; it is the baseline a VLM reviewer will ask for.

Prediction for our arms: adaLN's gain is mostly access form plus zero-init; the
conditioning-block and two-stream gains are the most likely to be extra
capacity. The designs that test this are E1, E2 and E4 above, plus three the
literature adds: an access-form ablation at fixed sites (adaLN scale-only,
shift-only, gate-only, and per-layer zeroing at test time), zero-init on vs
off, and shared vs per-layer adaLN (PixArt and DiT-Air disagree on whether
per-layer is needed).
