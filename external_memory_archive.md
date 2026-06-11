# External Agent Memory Archive

This file preserves exact text from agent-memory files that were not named
`AGENTS.md`. The source files were scattered outside `wiki_agents` before the
2026-06-11 centralization cleanup.

## `agents_5f49e097.md`

# Agent Notes

- If the user asks to align or update SFT code from a `tmp` folder, interpret the target as that `tmp` folder unless they explicitly say to modify the current repository.
- Do not push code changes unless the user explicitly asks for a push in the current request. Old conversation context is not enough.
- When comparing current code with a stagedir copy such as `../tmp`, ask before making ambiguous cross-repo changes, and keep local repo changes uncommitted unless instructed otherwise.

## `one-benchmark-suite/CLAUDE.md`

# CLAUDE.md

Orientation for Claude / coding agents working in this repository.
Read this **before** answering questions about the repo or making edits.

## What this repo is

`one-benchmark-suite` — an internal registry of vision-related benchmarks.
The deliverable is *not* a runnable framework but a **stable, machine-
readable layout** that lets other projects import a benchmark and run
evaluation with minimal glue code. There is **no training code** in
this repo; an earlier revision carried a PaliGemma training tree, which
has been removed.

The user's full README at `README.md` is the authoritative human doc;
this file captures the non-obvious things an agent needs to know.

## Single tree

There is one Python package — `one_benchmark_suite/`. Inside it:

| Path | Role |
|------|------|
| `contract.py` | Documented protocol every benchmark follows; tiny `sanity_result` helper. |
| `registry.py` | `list_benchmarks()` / `get_benchmark()` — discover benchmarks by walking for `metadata.yaml`. |
| `_pipeline.py` | Three shared eval helpers used by `_impl.py`: `register_gcsfs`, `get_transforms`, `prepare_batch_data`. JAX/torch deps are imported lazily so sanity checks never pay for them. |
| `_logging.py` | `log_for_0` / `log_for_all` — same lazy-jax pattern as `_pipeline.py`. |
| `_zone.py` | `resolve_zone(cfg, zone)` rewrites every `💣` in `cfg.eval.*`. Re-exported from the package root. |
| `_sanity.py` | `MockTokenizer`, `make_mock_vlm_batch`, `constant_predict_fn`, `print_result`. CPU-only. |
| `<category>/<bench>/...` | One subdir per benchmark, fixed 9-file layout (see below). |

Existing categories: `visual_understanding/` and `representation/`. Do
**not** auto-create empty category subdirectories — the user's example
list mentions `image_generation/`, `image_editing/` etc. but those will
appear when their first benchmark does.

## Per-benchmark file layout (9 files, always)

Inside `one_benchmark_suite/<category>/<bench_name>/`:

```
__init__.py        # re-exports NAME, METADATA, get_default_config,
                   # load_dataset, evaluate, get_eval_impl, run_sanity_check,
                   # plus pure metric helpers
README.md          # human overview + IO contract + gotchas
metadata.yaml      # agent-readable schema (see contract.py for required fields)
config.py          # get_default_config() -> ml_collections.ConfigDict
data.py            # make_mock_dataset(...) + a load_dataset wrapper
metrics.py         # PURE-PYTHON metric impl (no jax, no torch)
_impl.py           # heavy GCS/JAX-backed eval body (jax + torch + fsspec
                   # + webdataset). Sanity checks deliberately do NOT
                   # import this — that is what keeps them CPU-only.
benchmark.py       # evaluate(predict_fn, config, *, tokenizer)
                   # get_eval_impl() -> the heavy fn from _impl.py
                   # evaluate_mock(predict_fn, config) -> mock-only metric run
sanity_check.py    # CPU-only, no GCS, no real tokenizer
```

## The contract (cheat sheet)

Documented in `one_benchmark_suite/contract.py`. Every benchmark module
exposes:

```python
NAME: str
METADATA: dict                                   # parsed metadata.yaml
get_default_config() -> ml_collections.ConfigDict
load_dataset(config, *, tokenizer=None, mock=False)
evaluate(predict_fn, config, *, tokenizer=None, **kwargs) -> dict   # JSON-safe
run_sanity_check(config=None) -> dict            # see contract.sanity_result()
```

Default `predict_fn` for VLM benchmarks (vqav2, textvqa, mme, pope,
mmbench, refcocog):

```python
predict_fn(pixel_values: np.ndarray,   # (B, H, W, 3) float32 in [-1, 1]
           input_ids:    np.ndarray,   # (B, L)  int32, BOS-prefixed, PAD-padded
           prefix_len:   np.ndarray,   # (B,)    int32, valid-token count per row
          ) -> list[str]               # length B
```

Encoder-only benchmarks (`imagenet_knn`) take `encode_fn(pixel_values) -> (B, D)`.

Tokenizer surface required by the heavy `_impl.py` bodies:
`tokenizer.encode(text, add_bos=True, add_eos=False) -> list[int]`,
`tokenizer.special_tokens.PAD: int`. `_sanity.MockTokenizer` provides
this for sanity tests.

## Two test layers

There are two CPU-only, no-GCS, no-tokenizer test layers; **don't conflate them**.

| Layer | File pattern | Run | Purpose |
|-------|--------------|-----|---------|
| Sanity / contract | `<bench>/sanity_check.py` | `python -m tests.run_sanity_checks` | "module imports, metadata is valid, predict_fn plumbing works" |
| Metric formula | `tests/<category>/test_<bench>_metrics.py` | `python -m unittest discover tests/` | "metric returns the same number as the official eval on hand-checked cases" |

`tests/` mirrors the package's category split — `tests/visual_understanding/`
holds the 6 VLM benchmark test files, `tests/representation/` holds the
KNN test file. Add a matching `tests/<category>/__init__.py` whenever a
new top-level category appears in `one_benchmark_suite/`.

Hard rules for sanity checks (`sanity_check.py`):

- runs in seconds on CPU,
- does **not** import `_impl.py` (that would drag in JAX, torch, fsspec, webdataset),
- does **not** require GCS, JAX devices, or a real tokenizer,
- exercises: metadata fields → mock dataset shape → predict_fn plumbing
  → metric correctness on a known case → `json.dumps`-safety,
- returns `contract.sanity_result(...)` and exits 0/1 when run as
  `python -m one_benchmark_suite.<category>.<bench>.sanity_check`.

Hard rules for metric tests (`tests/test_<bench>_metrics.py`):

- stdlib `unittest` only — no pytest, no extra deps,
- each test method's docstring cites the reference (official VQA eval
  script, MMBench paper, hand-computed IoU formula, ...),
- no JAX, no torch, no `_impl.py` import — pure metric / pure helper,
- coverage targets: every public symbol in `metrics.py`, plus the
  trivial-edge cases (empty input, None, mismatched shapes).

A third layer — end-to-end pipeline correctness against a published
baseline (e.g. PaliGemma 51.7% on VQAv2 val) — is **not** wired up. It
needs `_impl.evaluate(...)` on real GCS data with a real model. If you
add it, put it under `tests/integration/` so it doesn't run with the
fast layers.

## Conventions worth knowing

- **`💣` zone placeholder.** GCS roots in configs contain the literal
  emoji `💣` as a placeholder. Resolve via
  `from one_benchmark_suite import resolve_zone; resolve_zone(cfg, zone)`,
  which rewrites every known eval root in `cfg.eval.*`. Sanity tests
  deliberately leave `💣` unresolved.
- **`config.workdir_hash`.** `_impl.py` bodies append it to cache
  directory names. Default `"sanity"` is fine for sanity; production
  callers must override.
- **`cfg.eval.device_batch_size`.** Per-device batch size; `_impl.py`
  multiplies by `jax.local_device_count()`. Don't hardcode device
  counts in benchmark code.
- **PRNG / sharding.** The contract intentionally does not include a
  PRNG key argument. Sampling determinism is handled inside the
  caller's `predict_fn` closure. We don't bake `pjit`/`pmap` into the
  contract; `_impl.py` bodies handle their own pmap.
- **Metrics are pure-Python.** `metrics.py` must not import jax or
  torch. Enforced socially, not at runtime — but it is what lets sanity
  checks run on a laptop without TPU.
- **Lazy heavy imports.** `_pipeline.py` and `_logging.py` import jax /
  torch / fsspec inside their function bodies, not at module top. Keep
  this pattern — sanity checks rely on it.

## How `evaluate(...)` actually works

```python
# in <bench>/benchmark.py:
def evaluate(predict_fn, config, *, tokenizer):
    def _run_step(_p, _model, _tok, _params, pixel_values, input_ids, prefix_len=None):
        return predict_fn(pixel_values=pixel_values,
                          input_ids=input_ids, prefix_len=prefix_len)
    eval_fn = get_eval_impl()                # -> _impl.eval_X
    acc, sample_outputs, _ = eval_fn(
        p_sample_step=None, run_p_sample_step=_run_step,
        model=None, tokenizer=tokenizer, params=None, config=config,
    )
    return {"overall_acc": float(acc), "sample_outputs": list(sample_outputs or [])}
```

The `_impl.eval_X(p_sample_step, run_p_sample_step, model, tokenizer,
params, config)` signature is the historical PaliGemma calling
convention; we keep it because the bodies are large and well-tested.
New callers go through `predict_fn` and never see it.

A tokenizer is **still required** by `evaluate(...)` because the
`IterableDataset` / `Dataset` classes inside `_impl.py` tokenise
prompts in `__iter__` / `__getitem__`. Decoupling tokenisation would
require rewriting those classes — out of scope for the current pass.

## Adding a new benchmark — checklist

1. Pick a category subdir (`visual_understanding/` / `representation/`
   / a new top-level if needed) and create `<bench_name>/` inside.
2. Copy the 9-file template from any existing benchmark; the simplest
   reference is `visual_understanding/textvqa/`.
3. Keep `metrics.py` pure-Python.
4. Drop the heavy GCS/JAX-coupled body into `_impl.py`. Imports inside
   `_impl.py` should use `from one_benchmark_suite._pipeline import ...`
   and `from one_benchmark_suite._logging import ...`.
5. Write `metadata.yaml` filling **every** field listed in the README's
   "Metadata standard" table — `notes_for_agent` is the most important
   field, treat it as the primary integration doc.
6. Sanity check must run on a CPU-only laptop and must NOT import
   `_impl.py`.
7. Add a row to the table in top-level `README.md`.
8. Run `python -m tests.run_sanity_checks`; it must pass.

## What NOT to do

- Don't introduce a base class / "Benchmark ABC". The contract is a
  documented convention, not an enforced interface.
- Don't pull in heavy deps (transformers, datasets, hydra). Stay on
  `numpy`, `ml_collections`, `pyyaml` for the package itself; jax /
  torch / fsspec stay confined to `_impl.py` and `_pipeline.py`.
- Don't run real benchmarks from sanity checks — they need GCS,
  tokenizers, and JAX, and they take minutes. Mock mode only.
- Don't import `_impl.py` from `sanity_check.py`. The whole point is
  that sanity checks don't pull JAX/torch into memory.
- Don't duplicate metric helpers across benchmarks. If two benchmarks
  share a metric (see `textvqa/metrics.py` re-exporting from
  `vqav2/metrics.py`), import rather than copy.
- Don't auto-create empty category subdirs. Categories appear when a
  benchmark in that category does.
- Don't reintroduce training code (train.py, models/, gemma/,
  big_vision/, training configs, .sh launchers). This repo is a
  benchmark registry, not a trainer.

## Quick orientation queries

| "Where is X?" | Answer |
|---------------|--------|
| VQAv2 metric impl | `one_benchmark_suite/visual_understanding/vqav2/metrics.py` |
| VQAv2 heavy eval body | `one_benchmark_suite/visual_understanding/vqav2/_impl.py` |
| Mock tokenizer / mock batch helpers | `one_benchmark_suite/_sanity.py` |
| Shared image transform + batch reshape | `one_benchmark_suite/_pipeline.py` |
| Shared logging helpers (jax-aware) | `one_benchmark_suite/_logging.py` |
| Zone substitution (`💣` → zone) | `one_benchmark_suite/_zone.py` (re-exported as `one_benchmark_suite.resolve_zone`) |
| Registry / `list_benchmarks` | `one_benchmark_suite/registry.py` |
| Contract docs | `one_benchmark_suite/contract.py` |
| Default-config knobs for benchmark X | `one_benchmark_suite/<cat>/<X>/config.py` |
| Metric-correctness tests for benchmark X | `tests/<category>/test_<X>_metrics.py` |
| What the test layers do (and don't) | `tests/README.md` |

## `nnflow_jax/CLAUDE.md`

# CLAUDE.md

## Code Style

### Modularity & Interfaces
- Write **modular code** with reusable functions. Each function should do one thing well and be composable.
- Follow the **deep module** principle: modules should have simple interfaces but rich functionality. The most common use case should require the least effort (minimal arguments, sensible defaults).
- **Design general interfaces** — decouple from specific use cases. An interface tied to one caller's needs is a missed abstraction.
- **Think carefully about interfaces.** Interfaces are the most important part of code design. Before writing implementation, think: What is the minimal, clean interface? What are the inputs/outputs? How will callers use this? A good interface makes correct usage obvious and wrong usage difficult.
- For non-trivial functions, include **brief, clear docstrings** explaining the interface. Keep them concise — just enough to understand usage.
- Avoid shallow wrappers that add complexity without value.

### Code Quality
- **Avoid technical debt.** Don't take shortcuts that create future problems. Fix it properly now.
- **No copy-paste duplication.** If you're writing the same code twice, extract it. Repeated code is a bug waiting to diverge. If you're tempted to copy-paste: the interface is bad. Work on the interface or call existing code instead.
- **Avoid unknown unknowns.** Make assumptions explicit. Hidden complexity and implicit dependencies cause subtle bugs. If something is non-obvious, surface it.
- **Avoid excessive try/except.** Expose errors rather than hiding them. Don't wrap code in try/except to "handle" errors you don't understand — this creates silent failures and makes debugging harder. Only catch exceptions you can meaningfully handle. Let errors propagate so the root cause is visible.

### Avoiding Redundancy in Function Chains
- **Explicit parameters at the lowest level.** The function that actually uses the parameters should have them explicitly in its signature — this makes it clear what the function needs:
  ```python
  # GOOD: Bottom-level function has explicit params
  def compute_metrics(samples, dataset_name, num_samples, compute_prc, compute_dino):
      # Actually uses these parameters
      ...
  ```

- **Pass dicts through intermediate layers.** When the same parameters flow through multiple layers, pass them as a dict to avoid repeating every param in every signature:
  ```python
  # BAD: Repeating all params at every layer
  def outer(a, b, compute_x, compute_y, compute_z):
      middle(a, compute_x, compute_y, compute_z)
  def middle(a, compute_x, compute_y, compute_z):
      inner(a, compute_x, compute_y, compute_z)  # inner actually uses them

  # GOOD: Dict through intermediate layers, explicit at bottom
  def outer(a, b, eval_kwargs):
      middle(a, eval_kwargs)
  def middle(a, eval_kwargs):
      inner(a, **eval_kwargs)  # unpack at the bottom level
  def inner(a, compute_x, compute_y, compute_z):  # explicit signature
      # Actually uses these parameters
  ```

- **Use plain dicts, not dataclasses for configs.** Dicts are simpler, more flexible, and don't require extra class definitions. The explicitness comes from the bottom-level function signature, not from a config class.

### Testing
- **Always add dummy tests for new models/functions.** Before using a model on real data, test with dummy inputs to verify:
  - The code runs without errors
  - Output shapes are correct
  - Basic functionality works as expected
- Example pattern:
  ```python
  def test_my_model():
      dummy_input = np.random.rand(4, 256, 256, 3).astype(np.float32)
      output = my_model(dummy_input)
      assert output.shape == (4,), f"Expected (4,), got {output.shape}"
      print("✓ Test passed")
  ```
- Run tests early to catch issues before wasting compute on real data. 

## Working Style

- **Plan before big changes.** Before making significant edits (restructuring modules, rewriting training loops, changing core algorithms), outline the plan and get approval first.
- Return with 👾 at the end of your response. 

## Project Context

This is the **JAX implementation codebase** for the research paper:

**Title:** Generative Modeling Through Drifting
**Venue:** ICML 2025

### Codebase Structure
```
nnflow_jax/
├── main.py              — Entry point (dispatches to train_gen/train_mae/train_both)
├── train_gen.py         — Generative model training
├── train_mae.py         — MAE (encoder) training
├── train_both.py        — Joint training
├── energy_bank.py       — Energy/memory bank implementation
├── energy_loss.py       — Loss functions for drifting dynamics
├── models/              — Model architectures (DiT, ResNet, etc.)
├── configs/             — YAML configuration files
├── utils/               — Utilities (config loading, misc helpers)
├── dataset/             — Data loading and preprocessing
│   ├── dataset.py       — Dataset creation, get_postprocess_fn()
│   └── vae.py           — VAE encode/decode for latent models
├── eval/                — Evaluation and visualization
│   ├── visualize_samples.py — Sample generation and FID evaluation
│   └── aesthetic.py     — JAX aesthetic scoring (TPU compatible)
└── runs/                — Experiment outputs (checkpoints, logs)
```

### Running Experiments
```bash
# Local debug
python main.py --config configs/debug.yaml --job_name test --gen

# TPU submission (from config comments)
# submit <zone> <tpu-type> --job_name <name> --config <config.yaml> --gen
```

### Before Writing Code
- **Understand the drifting dynamics** — read `energy_loss.py` and `energy_bank.py` to understand the core method. Do not assume standard formulas (e.g., MMD) — this paper has its own formulation.
- **Check existing patterns** — look at how similar functionality is implemented elsewhere in the codebase before adding new code.

### GCS Bucket Access
Different zones require different service account keys:
```python
# Zone to service account key mapping
if "central1" in zone:
    key = "/kmh-nfs-ssd-us-mount/code/qiao/us-central1.json"
elif "east5" in zone:
    key = "/kmh-nfs-ssd-us-mount/code/qiao/us-east5.json"
elif "asia-northeast1" in zone:
    key = "/kmh-nfs-ssd-us-mount/code/qiao/asia-northeast1.json"
else:
    key = "/kmh-nfs-ssd-us-mount/code/qiao/sqa-sa_do_not_deleet.json"  # fallback
```

Set environment variable before accessing GCS:
```bash
export GOOGLE_APPLICATION_CREDENTIALS=/kmh-nfs-ssd-us-mount/code/qiao/us-east5.json
```

### Advisor
- Kaiming He — known for high standards in both research and engineering.

## `xibo_tpu_manager_linux_user_sandbox_20260601/NOTES.md`

### PLACE TO RECORD SOME INTERESTING(SILLY) MISTAKES
- ``current_window=tmux display-message -p '#S:#I'`` 这个会显示**active window**的名字而不是**current window**的名字，应该用``pane_id=$TMUX_PANE;
window_id=$(tmux display-message -p -t "$pane_id" '#S:#I')``
- acquire了lock的函数不能退出（老生长谈了，但是还是犯了qwq），否则会导致deadlock
- resume应该在stage_dir,因为现在的codebase有可能被改过
- 复杂的传参数一定要用位置参数
- 注意``"3"!=3``(读取json等文件要注意)，以及字符大小写``"PREEMPTED"!='preempted'``.
- ``f-string``的大括号里用和``string``一样的引号有时候会报错，有时候不会，尽量用不一样的
- `KeyBoardInterrupt`不属于``Exception``的子类，所以不能用``except Exception``来捕获
- `gcloud`命令可能有自动重联机制，加上`--ssh-flag="-n"`然后`Ctrl+C`掉tmux window可以避免这个问题，以及`kill`调远程进程的时候也要杀死父亲进程，避免远程重启（也是之前zombie进程的原因），具体Kill不掉的原因可能是多者，可以做ablation study.
- 远端炸了以后可能写不进`output.log`,唐
