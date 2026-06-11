# Project Agent Index

This workspace contains many project checkouts. Agent memory has been
centralized in this folder so a new agent can start from one place. This index
tells a new agent where to look first and which shared wiki file covers the same
topic.

Full verbatim snapshots of the discovered `AGENTS.md` files are preserved in
`project_agents_archive.md`. Verbatim snapshots of non-AGENTS memory files are
preserved in `external_memory_archive.md`.

## Always Read First

1. `/kmh-nfs-ssd-us-mount/code/qiao/work/AGENTS.md`
2. `/kmh-nfs-ssd-us-mount/code/qiao/work/wiki_agents/AGENTS.md`
3. This index and the matching topic file.
4. A project-local `AGENTS.md` if one still exists.

## Project Groups

| Project / path | What it is | Shared wiki to read |
|---|---|---|
| `jax_llava/` | Current JAX LLaVA training/data/eval code and LLaVA-1.5 reproduction memory. | `vlm_training.md`, `tpu.md`, `spreadsheet_logging.md` |
| `jax_llava_late_fusion_13_5ed73eb/` | Copy with the same JAX LLaVA project notes as `jax_llava`. | `vlm_training.md` |
| `jax_llava_late_fusion_22_5ed73eb/` | Copy with the same JAX LLaVA project notes as `jax_llava`. | `vlm_training.md` |
| `jax_llava_master_39b30fb_before_late_fusion/` | Pre-late-fusion JAX LLaVA snapshot with shared reproduction/checkpoint notes. | `vlm_training.md` |
| `PaliGemma-baseline/` | Current PaliGemma / PrefixMAE training baseline, two-stage curriculum, HSDP notes. | `vlm_training.md`, `tpu.md`, `spreadsheet_logging.md` |
| `beifen-Paligemma/` | PaliGemma worktree with full stateful dataloader and two-stage notes. | `vlm_training.md` |
| `eue3a5qr-sft-new-pipeline/` | SFT worktree copied from pretrain stagedir for WandB run `eue3a5qr`. | `vlm_training.md` |
| `beifen/` | Dataset upload and visual sanity report scripts. | `vlm_training.md` |
| `one-benchmark-suite/` | Benchmark registry package; not a training framework. | `project_agents_archive.md`, `external_memory_archive.md` |
| `tpu_manager/` | Local MONITOR queue/resume working copy for `sqa`. | `tpu.md`, `xibo_monitor.md` |
| `xibo_tpu_manager_linux_user_sandbox_20260601/` | Sandbox copy of the xibo manager with remote Linux user support. | `xibo_monitor.md`, `tpu.md` |
| `nnflow_jax/` | JAX implementation for "Generative Modeling Through Drifting". | `external_memory_archive.md` |
| `wiki_agents/` | Shared cross-repository operational memory. | this folder |

## Duplicate Rule Groups

- `jax_llava/AGENTS.md`, `jax_llava_late_fusion_13_5ed73eb/AGENTS.md`, and
  `jax_llava_late_fusion_22_5ed73eb/AGENTS.md` were identical at the time this
  wiki was reorganized.
- Several PaliGemma/JAX LLaVA worktrees share HSDP, SFT dataset, stateful
  dataloader, durable checkpoint, and queue semantics. Those shared rules are
  consolidated in `vlm_training.md`; still read the local file for worktree-
  specific baseline differences.
- `tpu_manager/AGENTS.md` and
  `xibo_tpu_manager_linux_user_sandbox_20260601/AGENTS.md` overlap but are not
  identical. `tpu_manager/` describes the active local MONITOR flow, while the
  xibo sandbox describes the broader manager architecture and remote Linux user
  implementation.

## One-Benchmark-Suite Rules

`one-benchmark-suite` is a stable machine-readable benchmark registry package.
Do not add training code, launch scripts, model trees, or broad framework
abstractions.

The legacy `CLAUDE.md` content is archived in `external_memory_archive.md`; it
is the detailed orientation for coding agents in that checkout.

Each benchmark directory should keep the 9-file layout:

```text
__init__.py
README.md
metadata.yaml
config.py
data.py
metrics.py
_impl.py
benchmark.py
sanity_check.py
```

`metrics.py` must remain pure Python / numpy and must not import JAX, torch,
transformers, fsspec, or webdataset. Heavy imports belong in `_impl.py` or lazy
helper functions. Fast tests are:

```bash
python -m tests.run_sanity_checks
python -m unittest discover tests/
```

Zone-dependent config paths use the literal `💣` placeholder; call
`one_benchmark_suite.resolve_zone(cfg, zone)` before real GCS evals.

## Beifen Dataset Operations Summary

See `vlm_training.md` for current upload counts and same-zone rules. The short
version: upload/report from same-region TPU VMs, use `/dev/shm` for staging,
upload tar shards only, and store grouped `qas`/`refs` per image.

## Nnflow JAX Summary

The legacy `nnflow_jax/CLAUDE.md` is archived in `external_memory_archive.md`.
Key reminders: keep interfaces deep and modular, avoid copy-paste duplication,
add dummy tests before real compute, understand `energy_loss.py` and
`energy_bank.py` before changing drifting dynamics, and choose GCS service
account keys by zone.

## Updating This Index

When adding a new checkout-level agent-memory file:

1. Add the project to this index.
2. If the rule is reusable across projects, add it to the relevant wiki file.
3. Regenerate or update `project_agents_archive.md` or
   `external_memory_archive.md` so exact source text remains preserved.
