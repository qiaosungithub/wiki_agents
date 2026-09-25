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

**Log every parcae / loopformer / ouro run from this line to the `looped nanogpt`
tab of its own workbook, `1zVNvnD8CshpT-gUzEmHZCKnAcmkf6wZHdDUu69LFPEo`.** That
workbook is a curated copy: superseded runs and non-best sweep points were
pruned, so it holds the rows worth comparing against. The same-titled
`looped nanogpt` tab in the EqR workbook
(`17pvrMbOKOKFiIa-eorO8Od12qc5JmrFCSXcXKeoe_u0`) is the unpruned history and is
read-only now, as is the older `Parcae unroll-optim (qiaos)` tab there. Because
the two tabs share a title, pick the workbook by ID first and only then the tab
by title. `../research/result_logging.md` §Which Tab owns the routing rule and
the write mechanics.

