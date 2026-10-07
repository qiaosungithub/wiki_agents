# Workspace Policy

This page owns the rules that apply to every task. Each rule below is enforced
in full by the guide named beside it; these are the ones expensive enough to
state twice. Its sibling pages are [engineering.md](engineering.md) (the
working method) and [evidence.md](evidence.md#evidence-order) (the evidence
rules).

## Global Rules

**With the user — write plain language, not agent jargon.** Converse in Chinese;
write artifacts in English, except paper reports ([paper-reading skill](skills/paper-reading/SKILL.md)). Lead
with the outcome, and say it the way you would to a colleague who does not read
your logs. Name the thing that happened rather than the internal token for it:
"the job never started" beats "BUILD_REQUESTED never transitioned". Spell out an
identifier the first time it appears, keep literal names (`PROD`, an XID, a cell)
because they are what the user greps for, and cut the rest. [maintain-wiki skill §Maintaining Memory](skills/maintain-wiki/SKILL.md#maintaining-memory)
carries the same rule for what you write into these files.

**Never destroy the user's work.** Do not revert, overwrite, or clean a dirty
worktree as collateral. Before deleting anything shared, identify the
filesystem, owner, active references, and recovery path; use a manifest for bulk
deletion ([harness/engineering.md §External writes are transactions](engineering.md#external-writes-are-transactions)).

**Committing.** git push is your friend. You can push regularly, but need to be
careful which branch to push.

**Debug locally on CPU first.** After any large code change, run the whole path
(training step, logging, visualization, checkpoint save/restore, online and
offline eval) on CPU with the repo's `local_debug` config and
`scripts/local_debug.sh` before spending a remote round trip. Remote debugging
is slow, and most of what dies on the accelerator dies on a workstation too
([local-debug skill §Local debug, then remote, before a real run](skills/local-debug/SKILL.md#local-debug-then-remote-before-a-real-run)).

**Jobs.** On this SHARED workstation, submit through `tpu enqueue`; the
always-running TPU dispatch-worker (kept alive by the `*/2` ops watchdog) is the
SOLE builder and drains the queue by itself — do NOT start a `tpu build-worker`,
a second builder only spins refusing the per-queue singleton lock. That single
serial builder is what dodges the concurrent-build zombie XID. Use `tpu queue`
one-shot only when no other build is in flight.
Never call `xm launch` / `xmanager launch` directly ([knowledge/infrastructure/cluster-jobs.md §The launcher, config, and packaging](../knowledge/infrastructure/cluster-jobs.md#the-launcher-config-and-packaging)).

**Never train on BATCH.** Every TRAINING job passes `--tier=PROD` explicitly.
`BATCH` is a paying best-effort tier: it bills the group, it is not the free
option, and any PROD demand preempts it the instant a slot is contested. A
training run on BATCH is silently starved and still costs.

**The converse is NOT a rule: an eval may run on either tier.** `BATCH` is the
polite default for evals because it leaves the PROD budget bar to training, but
an eval that must actually finish belongs on PROD. This rule list and [knowledge/infrastructure/cluster-jobs.md](../knowledge/infrastructure/cluster-jobs.md) used
to carry "BATCH is EVAL-ONLY" / "Run evals only on BATCH"; the operator states
plainly (2026-09-07) that they never asked for that — their rule is and always
was **train on PROD only**. The invented half cost real time: the FID 50k evals
(50,000 generated images each) were preempted repeatedly on BATCH before being
moved ([knowledge/infrastructure/cluster-jobs.md §Tiers: train on PROD, evals either way](../knowledge/infrastructure/cluster-jobs.md#tiers-train-on-prod-evals-either-way)).

**A chip count is not a size.** Per chip, `v7 = v6p ≈ 2.17x v6e ≈ 4.34x v5p ≈
7.23x v4 ≈ 10.09x v5e`, so matching a `v6p-16` needs a `v6e-32`. Asking for
`v6e-16` silently buys HALF the compute, and the run is then compared as if the
hardware were equal. Do not round these ratios: rounding is the same mistake as
matching on chip count, one order of magnitude smaller. `tpu route --power=`
does the arithmetic, and [knowledge/infrastructure/tpu-reference.md](../knowledge/infrastructure/tpu-reference.md) owns the table (both are generated
from `router.py::_V5P_MULTIPLIER`; never hand-copy a third version).

**Storage.** Keep compute and storage co-located; a job far from its data is
killed by the pruner, not merely slowed. Never move Type 1 payloads across
regions ([knowledge/infrastructure/storage.md](../knowledge/infrastructure/storage.md), [knowledge/codebases/projects.md](../knowledge/codebases/projects.md) for the category).

**Cell -> metro -> bucket comes from one measured table**, `cell_locality.py`
(seeded from `mach_locality`, regenerable via `remeasure_cell_locality.py`).
Never hand-write another copy and never guess. A fallback that returned the cell
name as its own metro made `--metro` silently drop valid cells (it reads as "no
capacity"), and a `_DEFAULT_BUCKET` fallback put a job's writes a continent away
until the pruner deleted it. Resolve buckets by metro, not by cell, and make an
unknown cell fail closed ([knowledge/infrastructure/storage.md §Never Hand-Maintain A Cell -> Metro -> Bucket Table](../knowledge/infrastructure/storage.md#never-hand-maintain-a-cell---metro---bucket-table)).

**A checkpoint path is opaque; four shapes coexist**, including a torch
`step_<N>.pt` that is a FILE, not a directory. Replay the producer's own string
byte for byte; appending or stripping `/state` breaks a family. Read a
checkpoint from anywhere, but write only to local storage: a training loop
writing cross-metro is ~94x slower, drops duty cycle under the 0.20 floor, and
the pruner deletes the job mid-run ([knowledge/infrastructure/storage.md §A Checkpoint Path Is An Opaque String, And Four Shapes Coexist](../knowledge/infrastructure/storage.md#a-checkpoint-path-is-an-opaque-string-and-four-shapes-coexist)).

**Resuming: pass the checkpoint in the env var `LOAD_FROM`, verbatim.** Never
via a config key, because which key it lands in differs per family, so writing
the key keeps working on most lines and silently cold-starts the rest. Never
normalize the path either, because four incompatible shapes coexist, including a
torch `step_<N>.pt` that is a FILE, not a directory. Point it at the leaf, and
clear it once the job writes its own first checkpoint; a pinned `LOAD_FROM`
overrides auto-resume forever and reads as training instability. Leave
`CHECKPOINT_BUCKET`, where the job writes, alone. Reading a checkpoint across a
metro is survivable; writing across one gets the job deleted by the pruner
([knowledge/infrastructure/resume-contracts.md §The `LOAD_FROM` Contract](../knowledge/infrastructure/resume-contracts.md#the-load_from-contract)).

**Logging results.** Re-read the tab's header and neighboring rows every time;
layout drifts and a stale column map mis-files a number without erroring. Place
the row before filling it, keep cells short, and treat formatting as part of the
result ([result-logging skill](skills/result-logging/SKILL.md)).

**Project-local instructions.** A repository's own `AGENTS.md` / `CLAUDE.md` is
authoritative for its code semantics. The shared infra, storage, and
external-write rules here supersede stale operational sections in old project
notes; surface a conflict rather than guessing.
