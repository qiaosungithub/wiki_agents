---
name: local-debug
description: Make a large code change fit the fleet's infra contracts, then debug it locally on CPU and with one small remote run before a real run; use after any large code change and before submitting a job.
---

# Writing And Running New Code

This skill relies on
[the new training package startup contract](../../../knowledge/infrastructure/resume-contracts.md#chapter-2--new-training-package-startup-contract)
for the contracts in full and on [knowledge/infrastructure/cluster-jobs.md](../../../knowledge/infrastructure/cluster-jobs.md) for how a job is enqueued;
the principles behind it are in
[harness/engineering.md](../../engineering.md).

The two low-level drills that a large code change must pass before it earns a
real run: make the code fit the fleet, then debug it locally, remotely, and only
then for real.

## Adapt new code to the fleet's infra

A training binary is not standalone: the scheduler, its auto-resume, and the CNS
evidence layer all read it from the OUTSIDE. A new package must meet six
contracts, or it launches and silently misbehaves — every one a "looks healthy,
produced nothing / trained wrong" failure that surfaces only in the loss curve.
[knowledge/infrastructure/resume-contracts.md §Chapter 2 — New Training Package Startup Contract](../../../knowledge/infrastructure/resume-contracts.md#chapter-2--new-training-package-startup-contract) owns them in full; the index:

- **Checkpoint layout** is a shape the fleet's parsers already register, and a complete checkpoint is distinguishable from an in-flight one by atomic rename.
- **Resume channel**: eval and warm-start read `LOAD_FROM`; a pruning training run resumes via `restart_from` + `restart_step`; fail closed on the wrong combination.
- **Boot banner** names the durable CNS out_dir in the form the evidence layer parses, and a resume logs `resumed from <path> at step <N>`.
- **Read/write split**: the binary takes its write dir from `$CHECKPOINT_BUCKET`, never from the read path (the classic ELT bug).
- **`main.py` fails closed** on every under-specified launch (missing config or workdir, an unresolvable resume path), never defaulting to a cold start.
- **Log mirror**: the job tees stdout+stderr to a durable per-attempt CNS text log before distributed init, and the mirror swallows its own errors.

Two delivery rules that hold across all of the above: pass every resume selector
through `--launch` (it arrives as an env var), never by shell inheritance
(silently dropped) nor as an undeclared `--flag` (FATAL at parse); and read a
checkpoint from any metro but WRITE only to the local one, because a cross-metro
write gets the job deleted by the pruner. Exact shapes and reference
implementations: [knowledge/infrastructure/resume-contracts.md](../../../knowledge/infrastructure/resume-contracts.md).

## Local debug, then remote, before a real run

After any large code change, run the whole path on CPU, then one small remote
run, and only then the real run. A remote round trip costs a build, a queue
wait, a schedule, and a stagedir; a CPU run costs minutes and catches most of
what dies on the accelerator.

**Local, on CPU.** Each repo carries the runner — `scripts/local_debug.sh`, or
the older `tpu_scripts/debug.sh` — so read yours before writing anything. Two
parts: force CPU with `JAX_PLATFORMS=cpu` set BEFORE `import jax` (pair it with
`XLA_FLAGS=--xla_force_host_platform_device_count=N` to simulate N chips in one
process), and point the binary at a `local_debug` config that shrinks
steps/batch/data but keeps every stage the real config has.

- Cover the side paths, not just the training step — logging, visualization, checkpoint save AND restore, online and offline eval — because that is where the remote-only bugs live.
- A checkpoint save is a multi-host collective, so run `--procs 2` where supported: a single process cannot exercise a barrier, and a non-chief rank that skips the save HANGS rather than fails.
- Give any distributed path a timeout, because a deadlock produces no traceback; and remember `/cns` paths reject stdlib `open()`.
- Make the run a POSITIVE test: print a token like `LOCAL_DEBUG_OK` on the last line and check for it, because a piped runner reports the wrong stage's status and a timeout kills the wrapper, not the child.

**Then remote, small.** Only once the local run is green, do one small remote
debug run as a separate step. It exists to catch what CPU cannot see — real
accelerator topology, cross-host collectives at true scale, and the launcher's
own argv and staging — not to re-find what the local run already covered.

**A remote debug run may enqueue with `--priority=1`, so it schedules ahead of
normal work (which sits at the default `priority=0`).** This is the one standing
exception to the rule that `--priority>0` is operator-only ([knowledge/infrastructure/cluster-jobs.md](../../../knowledge/infrastructure/cluster-jobs.md)): a
debug run is small and short and you are waiting on it interactively, so jumping
the shared queue costs the other jobs almost nothing. Keep it at `1` — that is
enough to lead the queue — and do not carry the flag over to the real run.

**Then the real run**, and not before both of the above are green.
