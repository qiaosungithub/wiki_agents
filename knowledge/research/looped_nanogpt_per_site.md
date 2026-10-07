# The idea page: looped nanoGPT + per-site optimization

**One shared research idea drives every experiment line: when a weight is reused
across loop iterations (call sites), give each call site its own normalized
gradient and then combine them, instead of letting autodiff sum the raw
gradients before the optimizer ever sees them.** Below is the research owner's
own formulation of the idea, plus the clean setting built to test it. It is the
intended story, not a claim that any single benchmark already establishes it.

## Story

What people did for optimization with weight sharing: autograd sums up grads
from each "loop", without looking into each of them.

The story:

- We should at least get each of them.
- Do whatever you like:
  - Orthogonalization
  - Momentum
  - …
- Extension of the scope of the optimizer.
- Enable new optimizer designs.

## Scope

我想要建立一个新的nanogpt setting for looped methods (task: language pretraining).
目前有三种主流的方法：参见parcae, loopformer, ouro三个代码库（是一个git仓库的3个branch）
这三类方法从来没有一个统一的recipe去做他们，也没有横向对比（虽然这不是我们主要的目的，但是搭一个干净的setting是我们想做的）。
我们主要使用exactly parcae nanogpt setting, 然后把loopformer和ouro的recipe移植过来，用同样的data protocol, 差不多的model design. 但是我们目前保留了一些每个方法的独家特性，比如residual / norm design, 比如有没有input injection, 比如prelude / coda，具体看代码.

## The three methods and where they live

**parcae, loopformer and ouro are three branches of one git repo,
`qiaosungithub/parcae-jax`, each checked out in its own local directory:
`~/work/parcae-jax`, `~/work/loopformer`, `~/work/ouro`.** The clean setting
keeps the parcae nanoGPT recipe as the shared base (same data protocol, close
model design) and ports the loopformer and ouro recipes onto it, while
preserving each method's distinctive pieces: residual / norm design, whether
there is input injection, prelude / coda. The code is the source of truth for
those per-method differences.

## Results tab

The default destination for this line is the `looped nanogpt (cleaned)` tab.
[Result workbooks](../environment/result-workbooks.md) owns its workbook identity,
legacy destinations, and routing. Use the
[result-logging skill](../../harness/skills/result-logging/SKILL.md) for the write
transaction, and resolve the live tab by title before writing.

## Reading curves under the trapezoid schedule

**Under the default schedule (`cooldown_frac 0.5`, lr linear to 0 over the
second half), compare arms only at the final point, and read mid-run curves
only between arms with the same core lr×wd.** Measured 2026-09-30 on the Parcae
left-align family (70 arms, `val/ppl_D8`, 6400 steps; evidence and scripts in
`work/tmp/cooldown_rank_20260930/README.md`):

| Fact | Number |
|---|---|
| Rank correlation with the final ranking while lr ≥ 40% of peak | ≈ 0 |
| Drop over the last 255 steps (lr 9% → 0), across arms | 0.19 to 0.49 ppl; Spearman with core lr×wd 0.95 |
| Same drop across three seeds of one arm | sd 0.003 ppl |
| Pairs whose leader flips between step 3072 and the end: same lr×wd / lr×wd ratio > 1.5 | 7 of 189 / 635 of 1166 |
| Seed sd of the final ppl | Parcae 0.038, Ouro 0.013 |

- The mid-run closeness is the illusion, not the final gap: a larger lr×wd buys faster progress and a higher noise floor, and the two cancel until the lr is gone (Andriushchenko et al. 2023; Kosson et al. 2024; Bergsma et al. 2025).
- Gaps under 0.1 ppl at the end need at least three seeds; the current top five of the family sit within 0.024 ppl of each other.
- Per-site methods shift the effective lr×wd (at the same nominal product, `skip` arms drop 0.035 ppl more in the last segment than `magma` or `wns`), so match the effective timescale, not the nominal one, before reading a gap as a method effect.
- Do not shorten the wait with the `cosine_hold` floor in `loopformer-persample/docs/BASELINE_SCHEDULE_SWEEP.md`: not decaying to zero loses loss and re-orders arms. If earlier read-outs are needed, add an EMA-weights eval or branch cooldowns from a constant-lr trunk.
