# The Idea Page: 3-Hyperparameter Muon for Weight-Shared Looped Models

## Current Story (2026-10-02 Pivot): Eliminating the 5-Hyperparameter Tuning Tax via F-Norm Retention

### 1. The Empirical Finding: Muon's Hidden 5-Hyperparameter Tax on Looped Models
In Prelude–Core–Coda looped language models, standard **3-hyperparameter Muon + AdamW** (`adamw_lr`, `muon_lr`, `muon_weight_decay` shared across Prelude, Core, and Coda) is consistently suboptimal across all three major training paradigms (**Parcae** single-exit, **LoopFormer** two-exit + consistency distillation, and **Ouro** all-exit).

To unlock Muon's true baseline performance (`dmfw ctrl`: canonical summed-gradient Muon direction $U = \text{NS}(\sum_k d_k)$), one must actually tune **5 hyperparameters** by decoupling the 14 shared Core 2D matrices onto their own learning rate (`plr` = `core_muon_lr`) and weight decay (`pwd` = `core_wd`):
- **Parcae (6.4k steps, 3 seeds)**: 3-param optimum `3.0744 ± 0.0021` (`alr=1e-2, mlr=3e-3, wd=0.2/0.3`) vs. 5-param optimum **`3.0713 ± 0.0012`** (`plr=2e-3, pwd=0.6`) / **`3.0715 ± 0.0007`** (`plr=1.5e-3, pwd=0.8`, full seeds) — a $\mathbf{-0.0031}$ nats ($2\sigma \sim 4\sigma$) gap.
- **LoopFormer (6.4k steps, 3 seeds)**: 3-param optimum `3.0643 ± 0.0012` (`alr=8e-3, mlr=2e-3, wd=0.4`) vs. 5-param optimum **`3.0613 ± 0.0014`** (`plr=1e-3, pwd=1.2`) — a $\mathbf{-0.0030}$ nats ($>2\sigma$) gap.
- **Ouro (6.4k steps, 3 seeds)**: 3-param optimum `3.0623 ± 0.0007` (`alr=1e-2, mlr=3e-3, wd=0.3`) vs. 5-param optimum **`3.0598 ± 0.0012`** (`alr=1e-2, mlr=2e-3, wd=0.3/0.4, plr=1.5e-3, pwd=0.8`) — a $\mathbf{-0.0025}$ nats ($>2.5\sigma$) gap.

Across all three methods, the 5-hyperparameter optimum exhibits two structural invariants:
1. **Core LR Reduction ($\text{plr} / \text{mlr} \approx 0.50 \sim 0.75$)**: The shared Core matrices require a smaller update step than non-shared Prelude/Coda matrices, matching the Frobenius-norm loss ratio ($\rho_{\text{fro}} \approx 0.52$) when conflicting per-site momenta are summed.
2. **Real Weight-Decay Preservation ($\text{lr} \times \text{wd}$)**: The large nominal `pwd` ($2\times \sim 4\times$ `wd`) primarily compensates for the reduced `plr` so that the actual per-step multiplicative weight decay $\eta \lambda$ on the Core does not shrink when its update step is scaled down.

### 2. Our Optimizer Formulation (3 Hyperparameters Only)
We sell **"matching the 5-hyperparameter Muon optimum using only the 3 standard hyperparameters (`adamw_lr`, `muon_lr`, `muon_wd`)"**:
- **Per-site Nesterov momentum**: For each shared 2D Core matrix $W$ with $K$ call sites, maintain per-site momentum $m_k \leftarrow \mu m_k + (1 - \mu) g_k$ and lookahead $d_k = g_k + \mu(m_k - g_k)$.
- **Summed-gradient Muon direction (1 NS per step)**: Compute $d_{\text{sum}} = \sum_{k=1}^K d_k$ and orthogonalize once: $U = \text{NS}(d_{\text{sum}})$ (for `upstream` NorMuon: Polar-Express NS + shared second-moment normalization on $d_{\text{sum}}$).
- **Frobenius-norm retention factor $f \in (0, 1]$**:
  $$\rho_{\text{fro}} = \frac{\left\|\sum_{k \in \text{active}} d_k\right\|_F}{\sum_{k \in \text{active}} \|d_k\|_F}$$
  Two variants under evaluation:
  1. **`raw` (`rho_fro-raw`)**: $f_t = \rho_{\text{fro}}$ directly (zero extra hyperparameters).
  2. **`ema` (`rho_fro-ema`)**: $f_t = \text{EMA}_\beta^{\text{bc}}(\rho_{\text{fro}})$ with $\beta = 0.9$.
  *(Note: any non-shared matrix with $K=1$ site trivially has $\rho_{\text{fro}} \equiv 1$.)*
- **Update Rule (Unchanged `lr * wd` + Scaled Update `f * lr`)**:
  - **Canonical Muon**:
    $$W \leftarrow (1 - \text{mlr} \cdot \text{wd})\,W - (f_t \cdot \text{mlr}) \cdot 0.2\sqrt{\max(\text{rows}, \text{cols})}\,U$$
  - **Upstream NorMuon (Official Parcae Recipe)**:
    $$W \leftarrow W - \text{mlr}\sqrt{\max(1, \text{rows}/\text{cols})}\,\Big(f_t \cdot U + \text{wd}_t \cdot W \odot \mathbb{I}[U \odot W \ge 0]\Big)$$
- **Overhead**: Zero extra Newton-Schulz iterations (same FLOPs as baseline Muon); the only extra cost is storing the $K$ per-site momentum buffers for the 14 shared Core matrices.

---

## Old Story (Archived — Do Not Modify `~/work/paper-with-agent/` Yet)
The files in `~/work/paper-with-agent/hie1/` (`hie1-paper-scope.md`, `looped-nanogpt-details.md`) and `~/work/paper-with-agent/hie2/` record the **old story** (designing per-site gradient/momentum re-weighting or multi-NS merging to outperform the 5-hyperparameter Muon baseline). Keep `~/work/paper-with-agent/` untouched as the old story archive unless explicitly instructed by the user; `hie1/looped-nanogpt-details.md` remains the reference for benchmark architecture and evaluation details.

## Where The Benchmark Code Lives

**The three loss designs live in branches/worktrees of `qiaosungithub/parcae-jax`:**

| Design | Branch | Checkout |
|---|---|---|
| parcae (clean + official repro) | `parcae` / `persite-stepsize` | `~/work/parcae-jax`, `~/work/parcae-stepsize` |
| loopformer | `loopformer` | `~/work/loopformer` (`origin` = local `~/work/parcae-jax`) |
| ouro | `ouro` | `~/work/ouro` |

Results are logged to `looped nanogpt (cleaned 2)` in workbook `1chHYhhEnTfgkKmLnZiC7jjoFCE-ywsDCxPLXFdSTl20` per `result_logging.md` §Which Tab.
