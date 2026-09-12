# Diagnosing A Failing Or Silent Job

How to tell what state a failing or silent job is really in, whether one XID is
still alive, why a job died with no log, and how to read its metrics back. Three
chapters: **Chapter 1** is how diagnosis works, **Chapter 2** is the
step-by-step probes, and **Chapter 3** is the launcher-side failures that
masquerade as scheduler failures. Part of the `jobs/` set; the hub is
`../jobs.md`. Siblings: `submit.md`, `resume.md`, `liveness.md`, `report.md`.

The order in one line: resolve the exact work unit and read its failure
classification before hunting a cause; a job with no log is reproduced locally,
never re-launched for logs it cannot produce.

---

## Chapter 1 — How Diagnosis Works

### Experiment state is not work-unit state

**Experiment-level "running" is not allocated hardware; only the work unit's
state, allocation, logs, and activity tell queued from executing.** Resolve the
exact experiment and work unit before you read anything into a status string.

### The classification tells you where the fix lives

**Read the failure classification before hunting a cause: a code-bug verdict
puts the fix in your source, so preemption or quota hunting only wastes time.**
Read the whole failure, not the final status string; an immediate failure with
no logs can be allocator, topology, packaging, or authorization.

### Launcher-side failures never reached the scheduler

**A job that never created a work unit, or a launch that produced no XID, never
reached the scheduler, so the fault is workstation-local — not an allocator or
quota rejection.** The catalog of these is Chapter 3.

### What a missing log proves

**A death with no readable log has two readings — it reached `main()` or it
never did — and a startup marker is what tells them apart.** Three signs point to
a pre-`main()` death: an empty status message, no application log anywhere
including mirrors, and no surviving job handle. A numbered marker written as the
first action in `main()` splits them: present means execution reached `main()`
and the cause is downstream; absent means death before logging, or a cell too
over-quota to write its first line. `VMGROUP_STATE_RUN` with an empty status,
zero output, and no readable log is not necessarily a pre-`main()` death, only
one you cannot see. Two failure modes fire only remotely, past a green build and
smoke test: standard-library file APIs on a distributed path (`liveness.md`
§Identity, Paths, And Local Disk On A Worker) and mocked third-party libraries
the build stubs out (`../engineering.md` §Long-lived processes and the long
path).

---

## Chapter 2 — Diagnosing A Job, Step By Step

Work top-down from `tpu check`: resolve the exact experiment and work unit, then
read its failure classification by running the checker binary directly (its cache
refreshes about once a minute); blank on a pending job means "queued, nothing
wrong". If the error explicitly names expired credentials, ask the user to
re-authenticate and retry; not every access failure is credentials. If log access
still fails with a valid identity, read the work-unit status message via the
supported API or checker tools — never hard-code job ids in shared scripts, nor
assume another API skips authorization.

### Is one XID still alive?

**A bare `xmanager.par …` exits 127 — `xmanager` is a shell function and
`xmanager.par` is NOT on `PATH` — and behind a `| grep` that reads as "the job
is gone".** Never pipe the query: a pipeline reports its LAST stage's exit
status, hiding a missing binary as success-with-no-output.

```bash
# Preferred: self-documenting, prints Status, no side effect on a live job.
source ~/work/tpu_cmd/tpu_wrapper.sh
tpu cancel --dry-run <xid>

# When sourcing the wrapper is inconvenient: ABSOLUTE path, capture rc.
XM=/google/bin/releases/xmanager/cli/xmanager.par
out=$("$XM" list --experiment_id=<xid> --archived=no \
        --columns=ID,Name,Status,FailedWorkUnits 2>&1); rc=$?
echo "rc=$rc"; echo "$out"
```

Note the `/cli/`: `/google/bin/releases/xmanager/xmanager.par` does not exist.
Both commands exit 0 for a nonexistent XID, so `rc=0` only means the query ran —
read the `Status` line. `NOT_RUNNING` covers success and failure:
`FailedWorkUnits 0/1` is a clean finish, `1/1` a failed one. Job registry,
archived predecessor, snapshot config recovery, and cancel-versus-clear are in
`../infra/tpu_cli.md`.

### Debugging A Job That Dies With No Log

**Reproduce locally first, before any launch that changes imports or
dependencies.** The staged package is an ordinary build target, so the cluster's
exact artifact runs on a workstation; `--help` suffices, because flags parse only
after every module-level import, so import failures surface in seconds. The
staged per-run SNAPSHOT (`.../eqr_run_<ts>_<hash>/`) is what ran, not your edited
workspace, so workspace line numbers can describe a file never run. It carries a
`BUILD`: `blaze build <snapshot_path>:main` with the job's argv takes ~40 s and
zero credits, and answers what probe launches and log instruments cannot — flag
arrival, torch load, beacon fire, startup latency.

**Reproduce in the RENAMED stagedir.** The launcher rsyncs only the CWD into
`.../eqr_run_<ts>/` and builds `//<stagedir>:main`, destroying the authoring-time
google3 module path. A hardcoded absolute import
(`from google3.<original.pkg.path> import sibling`) or a cross-package BUILD
`dep`/`data` label then names something ABSENT from the staged binary, and the
worker dies at import, before `main()`, with no marker and behind the log wall;
it builds locally only because that package is present there. Use the EqR-jax
`eqr_run_*` idiom: `sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))`
in the entry point, siblings imported by BARE name, sibling `.py` riding along in
a BUILD `data` glob (`strict_deps = False`) as relative SYMLINKS to one source of
truth (`rsync -aL` gives real files). `from . import x` fails: a `py_binary` main
runs as `__main__`, with no parent package. Verify by building
`//<a-renamed-throwaway-dir>:main` without the sibling package, then `--help`;
in-place testing proves nothing.

**When the worker's own logs are walled off, write your own and read them with
`fileutil`.** Restricted-LOAS blocks every worker-log service from a workstation
credential — `borg tasklog` (it SIGABRTs), `analog --remote`, and the
F1/`get_job` path all return `PERMISSION_DENIED` — so stop after the first. Write
a numbered startup marker as the first action in `main()`, one per stage, plus a
`try/except` dumping the traceback to CNS (`../storage.md` §Before Touching A
Payload: write a copy's evidence to the destination, not to a log). The remaining
log sources, most reliable first:

| Source | Caveat |
|---|---|
| Work-unit job state (cell, user, job name, task counts, status message) | Request detailed status explicitly, or it returns silently empty like a gone job. Task info is GC'd in minutes; the status message lasts far longer, usually with the exception. |
| App log mirrored to durable storage, teed from program start, flushed on error lines | Outlives task, work unit, and experiment, but covers only post-start failures. Often Borg's only log, so protect it (`../engineering.md`: handlers steal streams). |
| Log-tailing CLI | Works sometimes. |
| Log-search CLI | May be blocked by workstation permissions. |

A 0-byte log means never started or unable to write. Rule out an over-quota cell,
which looks identical after hours — log created, first write refused — using
artifacts timestamped long after launch to settle which (`../storage.md` §An
Over-Quota Cell Looks Like A Broken Program). Do not re-launch for logs a
pre-`main()` death cannot produce.

### Metrics And Curves

**There is no external experiment tracker; the internal equivalent stores scalars
in a table service and plots them in a dashboard service, both keyed by
experiment id.** Reading the curves back from the workstation is possible and has
three routes, bucket first (`../research/result_logging.md` §Reading The Curves
From The Workstation, which also owns the URL forms, how to verify a run actually
wrote metrics, and the settings easy to get wrong: explicit opt-in, rank-0 only,
periodic flush). A report that says "the workstation cannot read the datatable"
has skipped them.

### "Clean up a job" / "清理 job" means `tpu clear` — nothing else

**"Clean up a job" means `tpu clear <xid>`: archive one finished run off the
board AND out of the local queue. It never deletes data.** The phrase is
otherwise ambiguous across five unrelated tools (below), so treat `tpu clear` as
its single canonical meaning and ask before assuming any other.

`tpu clear <xid> [xid...]` archives (never deletes) the named run's board entry
to `~/.tpu_jobs_legacy.json` — config recovery still resolves an archived id —
AND archives its local-queue row into the SAME legacy record (`queue_row` key),
matching by XID. Cleared entries leave the board one daemon cycle (~60s) later.

**It archives only a FINISHED (DONE/FAILED) queue row and refuses a live one**
(QUEUED/BUILDING/SUBMITTED/RUNNING/HELD) — the row is the router's handle on a
job still on the cluster, and dropping it strands the work, exactly as
`tpu dequeue` refuses a live row. Stop a live job with `tpu cancel <xid>` first
(verify against XManager, not the queue), then clear it once it has ended. **There
is deliberately no `tpu clear all`** — a blanket sweep is the one un-undoable
mistake, so name the XIDs.

The other four "cleanup" senses are DIFFERENT operations with different owners —
never silently pick one when someone says "清理 job":

| Phrase might mean | Tool / action | Owner |
|---|---|---|
| Archive a finished run off the board + queue (**the default**) | `tpu clear <xid>` | this section |
| Stop a live job | `tpu cancel <xid>` | §`tpu cancel`, `liveness.md` |
| Drop a not-yet-live QUEUE row / un-HELD one | `tpu dequeue` / `tpu requeue` | `../infra/router.md`, `submit.md` |
| Reclaim local workstation disk | targeted `du` + safe delete | `../storage.md` §Local Disk Cleanup |
| Prune old CNS checkpoints (rarely needed) | `tpu gc` | `../storage.md` |

---

## Chapter 3 — Classic Bugs And Fixes

Each row is the symptom you see, the cause underneath it, and the fix.

### Launcher-Side Failures That Look Like Scheduler Failures

**A submit-path failure is workstation-local, so match the symptom here before
you blame the allocator.**

| Symptom | Cause | Fix |
|---|---|---|
| One `tpu queue` yields TWO experiments on one out_dir (two writers corrupt it); `~/.tpu_jobs.json` records one, so the survivor is unregistered | background launches take stdin from `/dev/null`; without `< /dev/null`, `nohup`/`setsid` reads EOF, re-loops, and SUBMITS AGAIN; piping `yes` segfaults the CLI | an attribution prompt needs only EOF, so `tpu queue … < /dev/null`; never pipe into a submit; confirm EXACTLY ONE with `"$XM" list --experiment_name=<name>`, rc captured |
| A RUNNING-forever zombie: experiment shell, "No work units found", no log dir, no out_dir | an anti-dup wrapper killed the launcher on `Experiment id: N`, which prints at creation, BEFORE the blaze build (minutes) and any work unit | only `Launched experiment N` (resume: `Added N work unit(s) to experiment`) means finished, both after the build and work-unit add; retry on that line's ABSENCE, and grep `Launched experiment|work unit\(s\) to experiment`, never `Experiment id:` |
| A healthy job reads as "launch failed"; `Launched experiment \K\d+` matches nothing | XManager ANSI-colors the output — `Launched experiment \e[1m\e[34m281839914\e[0m "name"` — so the ESC follows the space, not a digit | pipe through `sed 's/\x1b\[[0-9;]*m//g'` first; the same colors bite watchers reading step numbers, `SUBMITTED`, `Preempted.` |
| The submit dies with `SIGBUS` | `/tmp` is RAM-backed tmpfs; a repro's core dump fills it and the next writer dies on an unobtainable page | disable repro cores and check free space first; every `/tmp` byte is RAM stolen from cold imports |
| Bazel refuses to glob a package ("Absolute symlinks are forbidden"), and it persists after you fix the tree | a checkout that symlinks the shared launcher in trips the rule, and the package glob cache keeps the rejection | dereference the symlink when copying, then restart the build server |
| Every task dies in parsing before logging, and an unlimited restart budget churns forever writing nothing | the launcher forwards flags as a `key=value` dict: positionals are inexpressible and `store_true` arrives as `--flag=`, which argparse rejects | select subcommands with a valued flag and booleans with explicit values; `--app.<flag>=<v>` passes one flag verbatim |
| The fleet runs silently in the wrong mode | a flag defaulting to `""` collapses "absent" and "present but empty" into one default branch | default to `None`, and test all spellings |
| Tasks never log, leaving no diagnostic | no startup marker, and `$BORG_TASK_INDEX` is never set by XManager | write each task's identity and mode to distributed storage using the BCL `%task%` macro |
