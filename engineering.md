# Engineering Discipline

Owns the working method for changing code, diagnosing a failure, and reporting a
result in any checkout. The evidence rules for every task are `AGENTS.md`
§Evidence Order; each codebase's semantics are in `projects.md` and the page it
names; queueing is `infra.md`; disk space and artifact completeness are
`storage.md`.

Chapter 1 is the principles; Chapter 2 is the local-then-remote debug drill that a
large code change passes before a real run.

---

## Chapter 1 — Principles

### Before you change anything

**Reproduce the problem before you change anything; "no change needed" is a valid
outcome.**

- A failed reproduction is not proof, because an earlier partial fix produces the same silence.
- Prove the smallest thing that can fail locally before paying for a remote round trip (Chapter 2).
- Before claiming done, re-read the original request and check the complete output against it, not against your patch.

### Trust artifacts, not success returns

**A success return describes the command, not the result, so check the artifact
the next reader consumes.**

- An install or a green build proves packaging, not that the code runs, so import the artifact or run its `--help`.
- A CLI can reject your flag and still exit 0, so read the output of a state-changing command, not just its `rc`.
- After any edit, read the file back from disk with an instrument that answers the real question: `grep -c` proves text exists, not that a method is attached to its class.
- To test whether a path exists, use the return code plus non-empty stdout. Do not grep the output for the name, because an error message quotes the path, and do not merge stderr into what you test.
- Give a batch existence sweep one row known not to exist as a negative control, and treat "does not exist" and "exists but empty" as different answers.
- A pipeline that hides a failed stage, or a listing that a pipe truncated, is covered in `AGENTS.md` §Evidence Order.

### Make edits atomic

**A change that spans a definition and its callers belongs in one edit, because a
job queued in between stages the broken window, uncommitted files included
(`infra.md`).**

- Deleting a file means deleting every reference to it, so grep the name first.

### Diagnose from evidence, not the most available story

**Read the deepest relevant failure, not the last line, because an earlier OOM or
a swallowed exception is usually the real cause.**

- Distinguish a process that was killed from one that exited: the footprints differ and the fixes are opposite.
- A log's last line is not proof of life; its last write time is.
- A cause that does not move when the suspect moves is not the cause.
- Two broken things can be true at once, so a real problem next to the failure is not automatically its cause.
- No log and no handle means the failure happened before logging existed. Print a start marker as the first statement of `main()` so that the two readings separate.
- Before reading a 0-byte log as a silent crash, rule out a full disk (`storage.md`).

### A test that cannot fail proves nothing

**Write the negative control first: break one property and require the verdict to
flip.**

- Assert on the artifact the next reader consumes (an exit code, a file, a counter), not the nearest thing that moved.
- Test a fix at a larger input than today's, never a smaller one, because shrinking the input hides the slope.
- Put the freshness check inside the reader, or a statistic over a frozen file reads as converged.
- Force a selector to select nothing and then everything before trusting what it picked.
- Report a violation as a verdict, not an exception, so one bad item does not hide every other finding.
- Keep the slow obvious implementation and assert that the fast one equals it.
- Inject faults into a scratch copy, never a shared file, and put the restore in a `trap` so a kill still cleans up.
- Smoke-test with the argv the launcher actually generates, not a command line you typed yourself.
- Default an optional flag to `None`, not `""`, because `""` folds "absent" and "present but empty" into one branch; test every spelling a caller can send.
- When two gates decide the same question, make both call one predicate, or they drift apart.
- Test a verifier backwards: point it at a known-bad artifact and require it to fail.

### When a reading is wrong, fix the predicate, not the command

**A correction re-runs the measurement but does not fix a broken way of reading
it, so repair the predicate before re-running.**

- Re-check the subject too: in a dirty worktree, `HEAD` and the file on disk are different objects, so name which one you measured.
- When a second measurement contradicts the first, chase it, especially when the first one flatters you.
- A hedge does not make a number right; a second independent route does (`AGENTS.md` §Evidence Order).
- Correct a retracted number everywhere it landed, including a source comment that quotes it.

### Guards and diagnostics must not kill the job

**A guard, validator, or telemetry hook swallows its own failure and never raises
into a training or serving loop; a deliberate fail-fast assertion on a
correctness condition is not a guard.**

- A guard threshold is a claim about floats, not algebra, so evaluate it at extreme inputs: underflow makes `exp(-tiny)` round to exactly 1.0.
- Check whether a statistic is a max, a mean, or a sample before treating it as a property of the whole object.
- While diagnosing a stuck healer, read its state; do not invoke it, even with `--help`.
- A diagnostic probe is also load, so do not investigate a saturated machine by adding to its saturation.
- To silence a failed optional lock, write `{ exec 210>"$LOCK"; } 2>/dev/null`. A bare `exec 210>"$LOCK" 2>/dev/null` also sends every later stderr line of the script to `/dev/null`.

### Long-lived processes and the long path

**A short run does not validate resume, so budget one deliberate restart before
trusting a multi-hour schedule.**

- Code that runs every N steps fails N steps in, because a stubbed library raises at call time, not at import.
- A long-lived process keeps state your fix cannot reach, such as a half-initialised module in `sys.modules` or a path frozen in its argv.
- `AttributeError` where you expected `ImportError` means the module exists but is incomplete, not a version skew; a fresh process tells you which.
- After changing how anything is located or imported, name the long-lived processes that still carry the old argv and must be recycled.
- A running Python driver or copy loop keeps the code it loaded at start, so editing its file changes nothing until a restart. Never edit a running bash script in place, because bash reads it as it executes.
- A watcher that emits no alarm may be dead, not calm, so prove it ran before trusting its silence.

### External writes are transactions

**Treat any external write as a transaction: establish identity and target,
validate, write the smallest scope, then read it back.**

- Preserve the user's work: never revert or clean a dirty worktree as collateral, and use a manifest for bulk or shared deletion (`storage.md`).
- Never kill by pattern, because `pkill -f` matches the shell that runs it; resolve the pattern to PIDs and check each one first.

### Sharing one worktree

**When agents share one worktree, tell your own worker from a peer by matching
the argv task before you react to it.**

- `git commit -- <pathspec>` ignores the index and re-reads the worktree, so it sweeps in a peer's uncommitted hunk; put the pathspec on `git add` instead.
- Never leave anything staged, because a stray `git rm` gets swept into someone else's commit.
- Land a declaration with its implementation, or a config sets a field the code does not have yet.

### Porting between related checkouts

**Never sync a file wholesale between related checkouts; re-apply the change as a
hunk, or the copy silently reverts what the other side added.**

- Grep for the reader, not the setter, because a setting nothing consumes is worse than a missing one.
- A value can arrive from a checkpoint or from an environment variable such as `LOAD_FROM`, not only from a config file (`vlm_training.md`).

### A tool call only fires as a structured call

**An action written out as prose but not issued as a real tool call did not
happen, and nothing reports the failure.**

- If a turn's job is to do something, its payload must be actual tool calls, because prose moves no state.
- Confirm that a side-effecting call landed (the message is in the thread, the row is in the table) before you claim it.

### Communicating a result

**Lead with the outcome, keep the prose load-bearing, and say plainly what you did
not verify.**

- Define overloaded terms such as step, update, iteration, and cycle before using them.
- A number is meaningless without its protocol: what it counts, its unit, its denominator, what was held fixed, and whether higher is better.
- Separate what the evidence supports from what you inferred, and keep a pointer to the trace.

---

## Chapter 2 — Local Debug, Then Remote, Before A Real Run

**After any large code change, run the whole path locally, then one small remote
debug run on an idle card you own, and only then queue the real run.** A remote
round trip costs a staged snapshot, a queue wait, and a card, while a local run
costs minutes and catches most of what dies on the accelerator.

### Run the local debug runner first

**Run the checkout's `local_debug.sh` only from that checkout's root, because it
runs `sudo rm -rf` on a work directory built from the current directory.**

| What the VLM runner does | Detail |
|---|---|
| Clears state | `sudo rm -rf $WORKDIR` and `sudo rm -rf ./wandb`. `WORKDIR` is `$(pwd)/tmp/us-central1-local-debug`, except in `jax_llava`, where it is all of `$(pwd)/tmp` |
| Runs | `python main.py --config configs/load_config.py:local_debug` with `--mode local_debug`; `load_config.py:<mode>` reads `configs/<mode>_config.yml` |
| Picks the platform | `# export JAX_PLATFORMS=cpu` is commented out, so the runner uses whatever accelerator the machine has |

- To force CPU, set `JAX_PLATFORMS=cpu` before `import jax`, and add `XLA_FLAGS=--xla_force_host_platform_device_count=N` to simulate N devices in one process.
- The `local_debug` config should shrink steps, batch, and data but keep every stage the real config has. Read your checkout's copy before trusting that it does.
- Cover the side paths, not just the training step: logging, visualization, checkpoint save and restore, and online and offline eval. The bugs that appear only remotely live there.
- A single process cannot exercise a multi-host barrier, and a non-chief rank that skips a checkpoint save hangs rather than fails, so the remote run is the first place that shows it.
- Give any distributed path a timeout, because a deadlock produces no traceback.
- Judge the run by a token it prints only on success, not by the status of a pipe or a wrapper; a timeout kills the wrapper, not the child.

### Then one small remote debug run

**Once the local run is green, run `debug_remote.sh <vm> [zone]` from the checkout
root, once, on an idle card you own.** It catches what a CPU cannot see: real
device topology, cross-host collectives, and the staged code path. The VLM
checkouts share one script:

| Step | What it runs |
|---|---|
| Locate | `source config.sh`, then `source ka.sh` for `VM_NAME` and `ZONE` |
| Stage | `sudo rm -rf $STAGEDIR/*`, then an `rsync` of the checkout into `STAGEDIR=/$DATA_ROOT/staging/$(whoami)/debug-$VM_NAME-$ZONE`, excluding `tmp`, `.git`, `__pycache__`, `*.png`, `wandb`, `big_vision`, and `gemma` |
| Clear logs | `gsutil -m rm -r ${GCS_LOGDIR}` on `gs://${BUCKET}/qiao_zhicheng_hanhong_files/debug-${VM_NAME}-${ZONE}/log` |
| Clear the card | `pgrep -f '[m]ain.py' \| xargs -r sudo kill -9`, then `sudo rm -rf /tmp/tpu_logs` |
| Run | `main.py` on every worker with `--config=configs/load_config.py:${config_name}`, `WANDB_MODE=disabled`, and `/kmh-nfs-ssd-us-mount/code/hanhong/shared` prepended to `PYTHONPATH` |
| Judge | Each worker prints `__REMOTE_EXIT_STATUS__:<status>`; then `check_dataloader_state 3` counts dataloader state files, and the script prints `Remote debug three-stage smoke passed.` |

- It kills every user's `main.py` on the VM, so never point it at a card that runs someone else's job.
- Its verdict fails on any nonzero status but needs only one worker to print `:0`, so a worker that printed nothing still passes. Read each worker's status line yourself.
- `check_dataloader_state 3` is hard-coded for a three-stage `remote_debug` config. In `jax_llava`, run `debug_remote_full_pipeline.sh`, which runs `remote_debug_full_pipeline` fresh and then resumes it with `--config.load_from=${WORKDIR}`.

### Then the real run

**Queue the real run through `infra` only after both debug runs are green
(`infra.md`).** To hold a card for interactive debugging instead,
`infra debug --types=<type> --minutes=<n>` reserves one.
