# The `tpu` Tooling Itself

The `tpu` CLI, its checkers, cache daemon, job registry, and preflight
internals. Read this only when changing, rebuilding, or debugging the tool;
launching and inspecting jobs is `../jobs.md`, and the smart cell-picker and
serial build-worker are `router.md`. Native code and `~/work/tpu_cmd/README.md`
outrank this file for flags and workflows.

## Principle

### Two Halves, Two Repositories

**The tool is split across two repos because the build system forces it.** The
checker half imports google3 packages, depends on internal build targets, and
the daemon loops over its compiled binaries.

| Half | Location | Contents |
|---|---|---|
| Shell + launcher | `~/work/tpu_cmd/` | wrapper script, launcher, README |
| Built checkers | a google3 CitC path under `experimental/users/<user>/tpu_utils/` | money/quota/infra checkers, shared utilities, preflight (topology, capacity, market, router), probes |

**The google3 half cannot be symlinked out.** All three variants fail: an
absolute directory symlink is rejected, a relative one escapes the source root,
per-file symlinks fail at action execution. Only the reverse works, for
navigation: real files in google3, a symlink in `~/work` pointing at them.

Both halves are versioned, the google3 half through a separate git directory, so
the worktree stays put, the build is unaffected, and only a tiny pointer file
sits in the source tree. Do not unify them with one repo plus a symlink: git
records a symlink as the link itself, so committing it backs up none of the
files behind it. A checkout is also not a backup; until the checker half submits
to the depot, the git repo is the only recovery path. Verify with `g4 files
//depot/google3/experimental/users/<user>/tpu_utils/...`: "no such file(s)"
means the git repo is still the only copy.

### One Tool, Two Operators

**`npu` is `tpu` with a different registry, not a fork.** A collaborator (lyy)
works on this workstation under the same Unix account, so environment variables
express ownership. Every consumer reads them, defaulting to the old hardcoded
path: `TPU_JOBS_FILE`, `TPU_JOBS_LEGACY_FILE`, `TPU_CHECK_CACHE_FILE`,
`TPU_JOB_NAME_PREFIX`, and for the local-queue router `TPU_LOCAL_QUEUE_FILE`
(lyy's own queue) and `TPU_BUILD_WORKER_SESSION` (lyy's own `npu-build-worker`
tmux session). Unset, the tool behaves as before they existed.

**This is bookkeeping, not a boundary: same Unix user, same XManager account,
same quota.** The `lyy-` experiment-title prefix exists because the XM UI is the
one view that cannot see the registry split. Splitting the registry splits what
each operator *writes*, not what they *see* or can *touch*, so every consumer
reaching past the registry needs scoping by hand — and each of these shipped
broken because the split looked like it had covered them:

- **The board unions two sources with different scopes.** `check` merges the
  per-operator registry with the `infra_check` cache, which is per-account: it
  lists every experiment the Unix user owns, whoever launched it. Unioned blind,
  the guest's board showed all of the owner's runs. A scoped board keeps a job
  only if the operator's own registry records it or its name carries their
  prefix (the prefix survives the cache's name truncation because it sits at the
  front).
- `cancel` is destructive and was unguarded — it passed any XID straight to
  `xmanager stop`, so one mistyped digit stopped the other operator's job. A
  scoped operator may cancel exactly what their own board shows, and a mixed
  batch is refused whole.
- Auto-recovery managed the other operator's process. A stale shared cache plus
  one `npu quota` ran `tmux kill-session -t tpu-daemon` and killed it. The
  quota/money cache is legitimately shared, but the daemon writing it belongs to
  the account owner.
- A consumer that reaches past the registry may still read the owner's:
  `infra_check` reads a hardcoded `~/.tpu_jobs.json`, not `$TPU_JOBS_FILE`.
  Treat any unscoped path here as a latent instance of this bug.

**The owner stays unscoped on purpose**: whoever pays for the quota needs to see
and stop everything running on it; the partial view belongs to the guest. Scope
every new per-operator resource here too (the queue file and worker session each
shipped a collision until added). `scripts/test_operator_scope.sh` pins all of
it, with `xmanager` and `tmux` shadowed by shell functions so it touches nothing
real.

### The Cache Daemon

**Status commands read a cache file, so they are instant; the background daemon
refreshing it carries all the latency, and the commands warn when the cache is
stale — so a full daemon round must finish well inside the staleness
threshold.** Two structural rules follow:

- **Split the round into a fast lane and a slow lane.** Commands warn per cache,
  so a slow checker must not hold a fast one past the alarm. Cheap money and
  quota finish in ~40 s; infra_check scales with registry size (one serial RPC
  per tracked job), takes minutes, and runs detached behind a `kill -0` guard
  that skips a second pass while one is in flight. One `wait` barrier over all
  three once aged `money.txt` past its threshold during a long infra pass, with
  money's own data ready for seconds.
- **Run the checkers in parallel, not a serial chain.** Every checker
  cold-starts once, paying a substantial interpreter cost while its RPCs cost
  under a second; chaining pays that tax repeatedly. They share no state and
  write to disjoint outputs.

### Job Bookkeeping

**The live registry is the file `tpu check` renders from; an older predecessor
file is no longer written and survives only as a resume fallback.** Three
distinctions matter:

- **A terminal row is polling load, not just clutter.** infra_check issues one
  serial RPC per tracked job, so hundreds of never-migrating rows
  (`TERMINAL_RECONCILED`, `CANCELLED`) inflate the round for jobs whose state
  can never change again. The daemon filters terminal status out of its poll
  set, and archiving them keeps the live registry small; do both, since a fresh
  registry accretes them continuously.
- **Clear archives rather than deletes**, moving entries to a legacy file. Keep
  it: an entry is the only mapping from an experiment id back to its checkpoint
  bucket, staging directory, and launch log once the job and work unit are gone.
- **Cancel is not clear.** Canceling stops the experiment and pins the registry
  entry so the daemon's auto-retry can never resubmit an explicitly killed job;
  the entry stays on the board until archived.

### Error Classification And Auto-Retry

**The daemon parses launch logs and classifies failures into defragmentation
preemption, resource exhaustion, allocator rejection (the fallback for a failure
with no stated reason), and unknown.** Auto-retry is narrow on purpose: only a
guaranteed-tier job rejected by the allocator is retried, a few times, minutes
apart. That is the client resubmitting a new experiment — a different mechanism
from the in-job restart budget in `../jobs.md` — and it does not cover preempted
jobs. The daemon runs compiled binaries, so a source edit here does nothing
until you rebuild.

### Preflight Internals

**Preflight verdicts are layered cheapest-first:** an in-process topology
whitelist plus per-allocation minimum-slice rules; one availability RPC asking
whether any cell in this allocation and tier has enough obtainable chips; and a
headroom heuristic warning when remaining quota is thin (near-permanent and
low-signal on dynamic pools).

The router ranks surviving candidates by cap-blocked status (a blocked
combination is kept and explained, not silently dropped), verdict, group
preference, headroom, cost, and accelerator preference. **Group preference
(`_GROUP_PREF`) puts g3/g5 ahead of g9 at PROD**: g3/g5 are small dynamic pools
with their own credit balance, exempt from the G9 income/10 budget cap
(`budget.md`), so spending them first preserves the regulated G9 budget. It sits
above the economics (headroom/cost) but below blocked+verdict, so it never
promotes a non-runnable or lower-confidence placement to save budget, and it is
neutral at BATCH (one free pool). Headroom differs by tier on purpose: the
guaranteed tier uses remaining quota, the batch tier obtainable chips, because
the batch pass never consults a floor. A `--metros` allow-list is a hard
data-locality filter applied before ranking. Market data comes from the money
checker's cache each daemon round; when that cache is missing or stale it says
so and falls back to price-blind ranking rather than failing.

**Per-allocation minimum-slice rules are pool policy, not physical law.** A
slice below the minimum is a valid hardware topology, disallowed by the
admission config and rejected instantly; the batch tier typically allows down to
the architecture's own minimum. These rules live in a table in the preflight
code (`../tpu_reference.md`), updated when an allocation behaves differently.

## Usage

### Building And Rebuilding Checkers

**Rebuild all checker binaries in one `blaze build` invocation, with the plain
proven command.** Building a single target can publish an output namespace
holding only that target, and the daemon then reports failures that look like
data or auth bugs. Exotic flags each broke it: a `startup`-class option (e.g.
`--noenable_dbip_auto_opt_in`) placed after the subcommand is rejected at parse
time and must precede `build`; `--spawn_strategy=local` breaks a non-sandboxed
genrule in the graph. Copy the command the daemon already runs; do not decorate
it.

Self-asserting test scripts (they exit non-zero on failure instead of using the
test framework) must be declared as test targets. Declared as binaries they
never run, and the test command reports no tests found.

### Invoking npu

**The `npu` function sets its env vars with `local -x`, never a bare `export`.**
A plain export would leak into every later `tpu` in that shell and silently file
the owner's next job into the collaborator's registry. To verify a change to the
scoping, diff the full `tpu check` output against the pre-change script rather
than eyeballing it. A second registry needs a second daemon
(`run-npu-daemon.sh`): the board renders from `$TPU_CHECK_CACHE_FILE`, so with
nobody writing it every job there reads `SUBMITTED` forever while looking alive.

### Recovering A Past Run's Config

**A shell helper reconstructs any past run's config from its immutable staging
snapshot.** It reads the staging directory from the registry (falling back to
the legacy file, so archived ids still resolve) and copies the exact config out
of that snapshot, learning which file by grepping the launch log. That answers
"which config produced this run", and is why deleting a finished experiment's
config from the checkout is safe.

### Serializing Heavy Verbs: Separate Blaze And Hg Locks

**Keep Blaze serialization separate from Hg status.** The PATH shims delegate to
`~/.tpu_bin/serialize_heavy.sh`. Only Blaze takes `/tmp/host_heavy.<uid>.lock`;
Hg goes through `hg_status_guard.py` and its own `/tmp/hg_status.<uid>.lock`.
Sharing one lock let a single `hg status` block builds for 23 minutes. Neither
gate may reuse `/tmp/tpu_build.host.lock`, which covers an entire launch
including upload. Children do not inherit either lock; `TPU_SERIAL_HEAVY=0` opts
out. Status preserves native arguments, stdout, stderr and exit codes; rejects a
concurrent status query with exit 75; times out at 120 s with exit 124; and
imposes a per-workspace five-minute cooldown after a timeout. Do not read any
nonzero status result as a clean tree, and resolve the real executable from a
cached absolute path, since a PATH walk may itself stall on CitC.

### Metrics Tables

**Metrics tables expire after a long window measured from last access, renewing
on every read or write; pin one explicitly if it must outlive that.** The table
CLI does not work from this workstation — a restricted credential blocks the
service and every local binary hits the same wall. This is a workstation
limitation only; a job writes fine. Use the browser URLs in
`../research/result_logging.md`.

## Errors

### A Frozen Board Means The Daemon Lost Its cwd

**A long-lived daemon whose cwd is on the CitC FUSE mount dies silently when
that mount is recreated.** Its python children fail at `os.getcwd()` with
`OSError: [Errno 107] Transport endpoint is not connected`, every checker
outputs nothing, and the correct "only overwrite the cache when the new output
is non-empty" guard then keeps the last good board forever.

The symptom is plausibility, not an error: `tpu check` renders every job as
`SUBMITTED` (the cache-miss fallback), so the board looks like a queue that has
not started rather than one that stopped updating, while the process stays
alive, the loop turns, and the log scrolls. Diagnose by timestamp, not by
liveness: `ls -la ~/.tpu_check_cache.txt` against `date`; a `.tmp` file newer
than the cache and zero bytes is the signature, and `tmux capture-pane -t
tpu-daemon -p | tail` shows the real error. Restart with an explicit start
directory outside the mount, or the new process inherits the dead handle:
`tmux respawn-pane -k -c "$HOME" -t tpu-daemon '<the while-true loop>'`.

### The Heavy-Verb Shim Must Not Swallow stderr

**`exec 210>"$LOCK" 2>/dev/null` reads as "quiet the fd-210 open", but `exec`
with no command applies EVERY redirection to the shell permanently, and to
whatever it execs** — so blaze's progress stream, its "another command is
running" notice, and the dbip link vanish, and a build stalled on a CitC
snapshot is indistinguishable from a frozen terminal. Brace-group it: `{ exec
210>"$LOCK"; } 2>/dev/null`. Test each gate with a command guaranteed to fail on
stderr (for Hg, status outside a repo); a shim that prints nothing there is
swallowing.

### Fig status Is Not Necessarily Read-Only

**Fig's native auto-widen step scans the entire CitC manifest before applying
the file filter and may write tracking metadata** (one failing workspace
repeatedly tried to add 1,813 directories, most from historical build staging).
Adding `.` or ignoring untracked files does not bypass it. Keep generated
staging in a separate non-Fig workspace (the launcher defaults to `clip_probe`);
do not delete Fig metadata or restart shared srcfs to make status fast.

### Cache Daemon Failure Modes

**Every one of these makes a correctly-built binary look broken, or a healthy
daemon look stuck.**

- **Never `readlink -f` the build output symlink.** Its two hops have opposite
  lifetimes: the first is stable and worth pinning against a concurrent build,
  the second is republished per build with only that build's targets behind it.
  Collapsing both freezes the daemon in one build's namespace no later rebuild
  can reach, so binaries sit correctly built in `blaze-bin` while the daemon
  insists they do not exist. Pin one hop, re-resolve the rest at each use, and
  fall back to the live path.
- **Serialize every self-heal rebuild behind one shared `flock`.** A checker
  binary is objfs-GC'd after a while, and three paths rebuild it (the daemon's
  self-heal, a wrapper's on-demand rebuild, a periodic keep-warm). Fired
  together they race on the single blaze output_base and republish each other's
  namespace, so none publishes a clean binary and the checker stays frozen while
  `blaze build` appears to run non-stop. A non-blocking `flock` shared by all
  rebuild paths collapses the storm to one build; the losers skip. (This is the
  checker-rebuild instance of the output_base race that `router.md` cures for job
  builds with the serial build-worker.)
- **A keep-warm rebuilds only when the binary is missing.** A built binary
  survives a long time, so an unconditional periodic `blaze build` is overhead,
  and not free: blaze's `--shutdown_on_low_sys_mem` evicts the idle server under
  memory pressure, so each "up-to-date check" cold-respawns a multi-GB JVM heap
  that deepens the dip that evicted it. Steady state is a cheap liveness exec
  (the binary's own `--help`). A timed-out or killed probe is UNKNOWN, never
  proof the binary is missing; if the build mtime never moves across many
  keep-warm cycles, investigate whether those "rebuilds" were wasted work.
- **When the staleness alarm fires, check the round duration the daemon logs
  before believing its "credentials expired" hint**, which is a guess and
  usually wrong. A hint printed into a detached tmux pane is not a fix, and the
  auto-recovery restarts the session, never the problem.
- **The command re-renders the cache; it does not print it.** `tpu check` parses
  the daemon's cached table and rebuilds its own, so a column the daemon computes
  and writes stays invisible if the command's parser drops it. The per-cell
  `REGION` column lived in the cache for a long time while the command showed
  only `XID|STATUS|NAME|…|WHY`; the fix was in the parser, not the daemon. Before
  concluding "the tool does not collect X", run the daemon binary directly and
  diff its columns against the command's. Section layouts differ, so a parser
  must gate per-section on the column count, not a fixed index.
- **`AGE` is derived in the wrapper, not the daemon.** It is submit-age (queue +
  run) parsed from the timestamp baked into each entry's `logdir`/`bucket_cp_path`
  in `~/.tpu_jobs.json`, not Borg run-uptime; "how long has it actually been
  training" still comes from `STEP × sec/step`. Add a wrapper column by editing
  the per-section `*_headers`/`*_caps` lists and the matching `*_rows.append(...)`;
  no daemon rebuild needed.

### A Preempted Job Is Dead, Not Pending

**A preempted job is dead, not pending** (`../jobs.md` owns why: no restart
budget means the torn-down gang counts as a task failure). Rendering any work
unit whose message merely contained "preempt" as pending made dead experiments
look like they were queuing for hours. Terminal state must win over a substring
match, while a genuinely queued job preempted earlier is labeled as such.
