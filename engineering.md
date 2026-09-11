# Engineering Discipline

Method for changing code, diagnosing failures, and reporting results in any
checkout. Two chapters: **Chapter 1** is the principles — one sentence each, so
you can scan them all in a minute. **Chapter 2** is the concrete drill for
writing and running NEW code against our fleet. `projects/` owns each codebase's
semantics; `jobs.md` and `storage.md` own infrastructure; workstation upkeep
lives in `workstation.md` and `infra/`.

## Chapter 1 — Principles

Each line is a rule, not a story. The evidence that earned it is in git history;
what matters here is that none of it is buried.

### Before you change anything
- Reproduce the problem first; "no change needed" is a valid outcome.
- A failed reproduction is not proof, because an earlier partial fix produces the same silence.
- Prove the smallest thing that can fail locally before paying for a remote round trip.
- Before claiming done, re-read the original request and check the complete output against it, not against your patch.

### Trust artifacts, not success returns
- A green build proves the code compiles, not that it runs — import or `--help` the artifact.
- A CLI can reject your flag and still exit 0, so read the OUTPUT of a state-changing command, not just its `rc`.
- After any edit, read the file back and assert the change is actually on disk.
- Read it back with an instrument that answers your real question (`grep -c` proves text exists, not that a method is attached to its class).
- A cached green build describes the tree as it was when cached, so pass `--nocache_test_results` when the verdict is load-bearing.
- A shell pipeline reports its LAST stage's status, so `cmd | head` hides `cmd`'s failure — capture `rc` on the very next line.

### Make edits atomic
- A change spanning a definition and its callers belongs in ONE edit, or a sibling's build samples the broken window.
- Deleting a file means deleting every reference to it, so grep the name first and build with `--keep_going`.

### Diagnose from evidence, not the most available story
- Read the deepest relevant failure, not the last line, because an OOM or a swallowed exception upstream is the real cause.
- Distinguish "it was killed" from "it exited" — different footprints, opposite fixes.
- A log's last LINE is not proof of life; its last WRITE TIME is.
- A cause that does not move when the suspect moves is not the cause.
- Two broken things can be true at once, so a real problem next to the failure is not automatically its cause.
- Absence of evidence is evidence: no log and no handle means the failure happened before logging existed.

### A test that cannot fail proves nothing
- Write the negative control first — break one property and require the verdict to flip.
- Assert on the artifact the next reader actually consumes (an exit code, a file, a counter), not the nearest thing that moved.
- Test a fix at a LARGER input than today's, never a smaller one, because shrinking the input hides the slope.
- Put the freshness check inside the reader, or a statistic over a frozen file reads as converged.
- Force a selector to select nothing and then to select everything before trusting what it picked.
- Report a violation as a verdict, not an exception, so one bad item does not hide every other finding.
- Keep the slow obvious implementation and assert the fast one equals it.
- Inject faults into a `/tmp` copy, never a shared file, and put the restore in a `trap` so a kill still cleans up.

### When a reading is wrong, fix the predicate, not the command
- A correction re-runs the measurement; it does not fix a broken way of READING it.
- Re-check the subject too: in a dirty worktree `HEAD` and the file on disk are different objects, so name which one you measured.
- When a second measurement contradicts the first, chase it — especially when the first one flatters you.
- Hedging a number does not make it right; a second independent route to the same value does.
- Correct a retracted number everywhere it landed, including the source comment that quotes it.

### Guards and diagnostics must not kill the job
- A guard, validator, or telemetry hook must swallow its own failure and never raise into a training or serving loop.
- A guard threshold is a claim about floats, not algebra, so evaluate the expression at extreme inputs (underflow makes `exp(-tiny)` round to exactly 1.0).
- Check whether a statistic is a max, a mean, or a sample before treating it as a property of the whole object.
- While diagnosing a stuck healer, read its state; do not invoke it, even with `--help`.
- A memory cap without a swap cap is not a cap, so set `MemoryMax` AND `MemorySwapMax=0`.
- A diagnostic probe is also load, so do not investigate a saturated machine by adding to its saturation.

### Long-lived processes and the long path
- A short run does not validate resume, so budget one deliberate restart before trusting a multi-hour schedule.
- Code that runs every N steps fails N steps in, because stubbed libraries raise at CALL time, not import.
- A long-lived process keeps state your fix cannot reach — a half-initialised module in `sys.modules`, or a path frozen in its argv.
- `AttributeError` where you expected `ImportError` means the module exists but is incomplete, not a version skew, and a fresh process tells you which.
- After changing how anything is located or imported, name which long-lived processes still carry the old argv and must be recycled.
- Only `cron` + `setsid` survives on a workstation; a daemon from an agent or SSH shell is reaped when the session ends.
- A watcher that emits no alarm may be dead, not calm, so prove it ran before trusting its silence.

### External writes are transactions
- Treat any external write as a transaction: establish identity and target, validate, write the smallest scope, then read it back.
- Preserve the user's work — never revert or clean a dirty worktree as collateral, and use a manifest for bulk or shared deletion.
- Never kill by pattern; `pkill -f` matches the shell that runs it, so resolve to PIDs first.

### Sharing one worktree
- In an autonomous run, tell your OWN worker from a PEER by matching the argv task before you react to it.
- `git commit -- <pathspec>` IGNORES THE INDEX and re-reads the worktree, so it sweeps in a peer's uncommitted hunk — put the pathspec on `git add` instead.
- Never leave anything staged; a stray `git rm` gets swept into someone else's commit.
- Land a declaration with its implementation, or a config sets a field the code does not yet have.

### Porting between related checkouts
- Never sync a file wholesale; re-apply the local change as a hunk, or the copy silently reverts what the local side added.
- Grep for the READER, not the setter, because a setting nothing consumes is worse than a missing one.
- A value can arrive from a checkpoint or a merged `extra.json`, not only a config file.

### A tool call only fires as a structured call
- An action you "wrote out" as prose but did not issue as a real tool call simply did not happen, and it fails silently.
- If a turn's job is to DO something, its payload must be actual tool calls, because prose moves no state.
- Confirm a side-effecting call landed (the message is in the thread, the row is in the table) before you claim it.

### Communicating a result
- Define overloaded terms (step, update, iteration, cycle) before using them.
- A number is meaningless without its protocol: what it counts, its unit, its denominator, what was held fixed, and whether higher is better.
- Separate what the evidence supports from what you inferred, and keep a pointer to the trace.
- Lead with the outcome, keep the prose load-bearing, and say plainly what you did not verify.

## Chapter 2 — Writing And Running New Code

The two low-level drills that a large code change must pass before it earns a
real run: make the code fit the fleet, then debat it locally, remotely, and only
then for real.

### Adapt new code to the fleet's infra

A training binary is not standalone: the scheduler, its auto-resume, and the CNS
evidence layer all read it from the OUTSIDE. A new package must meet six
contracts, or it launches and silently misbehaves — every one a "looks healthy,
produced nothing / trained wrong" failure that surfaces only in the loss curve.
`jobs/resume.md` Chapter 2 owns them in full; the index:

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
implementations: `jobs/resume.md`.

### Local debug, then remote, before a real run

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

**Then the real run**, and not before both of the above are green.
