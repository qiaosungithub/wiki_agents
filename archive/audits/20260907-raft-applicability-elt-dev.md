# RAFT applicability, compute budget, and ELT DEV estimate

Follow-up on 2026-09-07 to the [backup survey](20260907-weight-sharing-backups.md).
ALBERT and RAFT remain the priority backups. CLRS and MoDL are deprioritized,
and SimCLR is excluded. No cluster training was launched or modified. The RAFT
checks below ran locally on CPU using a copy of the original implementation.

## Recognition and scope

RAFT won the ECCV 2020 best-paper award. TorchVision supplies both model sizes,
pretrained weights and training references. It fits the owner's requirement for
a broadly recognizable baseline. Sources: [ECVA awards](https://www.ecva.net/),
[TorchVision announcement](https://pytorch.org/blog/pytorch-1.11-new-library-releases/).

MoDL means Model-Based Deep Learning: a shared CNN alternates with data-consistency
solves for undersampled MRI reconstruction. It is a 2018 IEEE Transactions on
Medical Imaging method, useful for this mathematical mechanism but more
specialized than ALBERT or RAFT. Its earlier priority overemphasized graph
suitability relative to the owner's desired audience. Source:
[original paper](https://arxiv.org/abs/1712.02862).

CLRS is an ICML 2022 benchmark within neural algorithmic reasoning. Being a
formal benchmark does not give it equally broad recognition across ML; retain
it as a targeted option. Source: [proceedings](https://proceedings.mlr.press/v162/velickovic22a.html).
SimCLR is excluded because symmetric sharing across augmented examples primarily
tests view/batch partitioning, without the recurrent distance structure of this project.

## RAFT supports the proposed gradient decomposition

Original training uses 12 refinement iterations. Each iteration detaches flow
coordinates before correlation lookup, but carries the GRU hidden state without
detaching it. Every output receives supervised L1 loss, with coefficient
`a_j = gamma^(T-j)`; gamma defaults to 0.8, with 0.85 in later fine-tuning stages.
Sources: [forward](https://github.com/princeton-vl/RAFT/blob/master/core/raft.py),
[loss and defaults](https://github.com/princeton-vl/RAFT/blob/master/train.py).

| Parameter family | Earlier call affects later loss? | Intended treatment |
|---|---|---|
| Recurrent motion encoder | Yes, through the GRU state | Group by relative refinement distance |
| GRU | Yes, through the carried state | Group by relative refinement distance |
| Flow head | No, next iteration detaches its flow output | Aggregate all same-round contributions into distance1 before normalizing |
| Learned upsampling mask head, large only | No, output only forms that round's prediction | Same distance1 behavior |
| Feature/context encoders | Evaluated before the recurrent graph | Initially use ordinary optimization for this ablation |

For recurrent parameters, the owner's dense-loss definition becomes:

```text
G_n = sum over i with i+n-1 <= T: a_(i+n-1) * g_(call i -> loss i+n-1)
U_n = Normalize_n(G_n)
update = sum_n U_n/n / sqrt(sum_n 1/n^2)
```

Distance counts outer refinement rounds; n=1 is the same round's loss. Preserve
gamma in the objective before optimizer normalization. A readout with only a
distance1 group must not be divided by a 12-group denominator. Normalizing
per absolute call after summing all downstream losses is a different method.

Start with per-distance AdamW versus ordinary AdamW. Keep one shared forward
parameter value after every update, and apply decoupled weight decay once. Muon
would additionally require a documented convolution-kernel flattening convention.
No flow detach or hidden-state connection needs to change.

### Executable graph check

Downloaded original files with their license and [source hashes](../../../.weight_sharing_survey_20260907/raft/sources.json).
The [check script](../../../.weight_sharing_survey_20260907/raft/check_graph.py)
compares ordinary sharing against differentiable parameter copies with identical
values. It uses both model sizes, four iterations, synthetic 128x128 image pairs,
the weighted L1 reduction with all pixels valid, and frozen batch normalization.

| Check | Small | Large |
|---|---:|---:|
| Trainable parameters | 990,162 | 5,257,536 |
| Entire update-block parameters | 876,530 | 3,120,960 |
| Maximum forward difference | 0 | 0 |
| Max absolute error: sum of relative groups versus original shared gradient | 7.15e-7 | 2.38e-7 |

Call1's motion-encoder and GRU gradients from loss4 are nonzero. Call1's flow-head
gradients from loss4 are absent; the large model's mask-head gradients are also
absent. The check rejects future-call contributions to earlier losses.
[Full results](../../../.weight_sharing_survey_20260907/raft/graph_check.json).
This verifies paths and decomposition, not optimizer gains or GPU performance.

## RAFT training and computation budget

A standard published target already exists after **Chairs plus Things (C+T)**,
evaluated on Sintel/KITTI training splits held out from C+T. Later fine-tuning
stages are required only for the corresponding fine-tuned scores. The earlier
survey overemphasized the complete four-stage schedule. Small is also a published
architecture. Source: [paper supplement](https://www.ecva.net/papers/eccv_2020/papers_ECCV/papers/123470392-supp.pdf).

| Reference | C+T budget | Reference hardware |
|---|---|---|
| Original standard large | Chairs 100k, batch 10, 368x496; Things 100k, batch 6, 400x720 | 2 GPUs |
| Original mixed-precision large | Chairs 120k, batch 8; Things 120k, batch 5 | 1 GPU |
| Paper small | 160k total; exact stage split not recovered from generic scripts | 2 GPUs |
| TorchVision large reproduction | Roughly 100k per stage; effective batch 16 | 8 A100 GPUs |

Sources: [standard script](https://github.com/princeton-vl/RAFT/blob/master/train_standard.sh),
[mixed script](https://github.com/princeton-vl/RAFT/blob/master/train_mixed.sh),
[TorchVision reference](https://github.com/pytorch/vision/blob/main/references/optical_flow/README.md).
Batch, precision and data exposure differ; select one protocol for both arms.

The [count script](../../../.weight_sharing_survey_20260907/raft/count_work.py)
executes original model shapes on meta tensors, counting all convolution MACs
and the correlation matmul. One MAC is one multiply-add, or two FLOPs here.
Sampling, normalization, activations, upsampling, communication, input processing
and optimizer work are excluded. [Detailed counts](../../../.weight_sharing_survey_20260907/raft/work_count.json).

| One image pair, 12 rounds | Small forward GMAC | Large forward GMAC | Ratio |
|---|---:|---:|---:|
| Chairs368x496 | 32.73 | 146.01 | 4.46x |
| Things400x720 | 52.59 | 232.28 | 4.42x |

For equal 100k+100k schedules with batches 10/6, approximate forward-plus-backward
work is **0.386 EFLOP small / 1.712 EFLOP large**, assuming three forward-equivalents
per training step. This small schedule is a matched-budget proposal, not the
paper's 160k run. The FP32 correlation pyramid alone is about 41 MiB per pair on
Chairs or 102 MiB on Things, independent of model size; other activations and
gradients add memory. Small does not reduce every cost by 4.4x.

No authoritative elapsed C+T training time was found for these exact recipes.
This workstation has CPU-only PyTorch. The paper's 0.05s/0.10s numbers measure
**inference** after 10 updates on a 1080Ti, not training batches.

For synchronized step times `t_C` and `t_T`, standard C+T requires
`100000*(t_C+t_T)/3600` hours, then x2 for the requested allowance:

| Conditional average step time, not a hardware prediction | C+T training | With x2 |
|---|---:|---:|
| 0.10s | 5.56h | 11.1h |
| 0.20s | 11.11h | 22.2h |
| 0.40s | 22.22h | 44.4h |

Add setup, staging and evaluation if the measured window excludes them. GPU
count and parameter count alone do not establish which timing row applies.

### The exact multi-loss treatment has additional backward cost

Twelve supervised rounds give up to `12*13/2 = 78` call/loss pairs, combined
into 12 relative-distance groups. A direct per-loss vector-Jacobian implementation
traverses a triangular set of recurrent prefixes, versus 12 core visits in an
ordinary backward: approximately 6.5 times the core backward work. This is not a
6.5x whole-step multiplier or a lower bound for every possible implementation.

With a two-forward-equivalent backward approximation, efficiently aggregated
feature-encoder gradients and correctly limited readout paths, the counted shapes
suggest approximately 3.0x large or 3.9x small whole-step arithmetic for this direct
approach. Repeating full-graph backward can be worse; batched adjoints/custom
backward may improve execution. These are not measured GPU timing multipliers.

Use **RAFT-small, 12 rounds, unchanged sequence loss** as the initial target,
with a declared reference schedule and equal-budget control. Its roughly 4.4x
arithmetic advantage over large can absorb much of the decomposition overhead.
Final-loss-only would change the objective, and absolute-call normalization
would change the method; neither is a silent substitute for relative grouping.

## ELT DEV estimate, anchored to actual VAE work

The continued independent audit recovered XID 281302442: 1,281,167 ImageNet images
encoded on historically recorded v7-8 hardware in 1010 seconds, or 1268 images/s,
including image input, the same SD-v1.4 VAE, and 39.5 GB cache output. The 256px,
float32, posterior-mean path matches ELT. Producer batch/overlap were not recovered;
extra output writes make this a pipeline reference, not a pure-VAE lower bound.

DEV's `80000*256 = 20.48M` presentations correspond to 4.48h at that pipeline rate
on v7-8. Allowing 2–4x effective scaling to v7-32, small-trunk work, host overhead
and startup gives these **ordinary-Adam baseline estimates**:

| Hardware | Estimated training plus startup | With x2 | Single planning budget |
|---|---:|---:|---:|
| v7-32 | 1.5–4.5h; central 2–3h | 3–9h | **6h** |
| v7-8 | 4.5–8.5h; central around 6h | 9–17h | **12h** |

These are estimates, not DEV measurements or guaranteed scaling. The complete
scenario model and directly retrieved artifacts are in the
[DEV estimate report](../../../.weight_sharing_survey_20260907/elt_dev_estimate.md).
Proposed optimizer overhead is not included.

The budget assumes a fast-iteration variant moving repeated sample/FID evaluation
out of training. Unmodified author DEV runs 80k updates without early stopping,
eight validation/sample-grid rounds and four 50k-image FIDs with a 512-step DDPM
sampler. Those evaluations are unmeasured here. Raw-mode completion time therefore
adds them to the training estimate. No mode was changed during this audit.
