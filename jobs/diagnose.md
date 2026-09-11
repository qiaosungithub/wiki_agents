# Diagnosing A Failing Or Silent Job

Status and diagnosis order, checking whether one XID is still alive, debugging a
job that dies with no log, launcher-side failures that masquerade as scheduler
failures, and reading metrics and curves. Part of the `jobs/` set; the hub is
`../jobs.md`.

## Status And Diagnosis

1. From `tpu check`, resolve the exact experiment and work unit:
   experiment-level "running" is not allocated hardware. Work-unit state,
   allocation, logs, and activity tell queued from executing.
2. Read the failure classification first: a code-bug verdict puts the fix in
   your source, so preemption/quota hunting wastes time. Its cache refreshes
   about once a minute; run the checker binary directly. Blank on a pending job
   means "queued, nothing wrong".
3. Read the whole failure, not the final status string: immediate failure
   without logs can be allocator, topology, packaging, or authorization.
4. If the error explicitly names expired credentials, ask the user to
   re-authenticate and retry. Not every access failure is credentials.
5. If log access still fails with a valid identity, read the work-unit status
   message via the supported API or checker tools. Never hard-code job ids in
   shared scripts, nor assume another API skips authorization.

### Checking Whether One XID Is Still Alive

**`xmanager` is a shell function and `xmanager.par` is NOT on `PATH`; a bare
`xmanager.par ...` exits 127, which behind a `| grep` reads as "the job is
gone".** One line took three blank greps as three vanished jobs, all fine:

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
Never pipe it (`| grep`, `| head`): a pipeline reports its LAST stage's exit
status, hiding a missing binary as success-with-no-output.

Both exit 0 for a nonexistent XID: `rc=0` only means the query ran. Read the
`Status` line; silence answers only if it ran. `NOT_RUNNING` covers success and
failure: `FailedWorkUnits 0/1` is a clean finish, `1/1` a failed one.

Job registry, archived predecessor, snapshot config recovery,
cancel-versus-clear: `../infra/tpu_cli.md`.

"Clean up the finished runs" means `tpu clear`, not deleting data: ambiguous
word, unrelated tools. `tpu clear` tidies the BOARD, archiving (never deleting)
finished and failed entries to `~/.tpu_jobs_legacy.json`, which config recovery
still resolves. `tpu gc` sweeps CNS checkpoints. Use `clear` for a cluttered
`tpu check`, `gc` only for a filling cell; cleared entries leave the board one
daemon cycle (~60s) later.

## Debugging A Job That Dies With No Log

**Reproduce locally first**, before any launch that changes imports or
dependencies. The staged package is an ordinary build target: the cluster's
exact artifact runs locally. `--help` suffices: flags parse only after every
module-level import, so import failures surface in seconds.

Reproduce in the RENAMED stagedir. The launcher rsyncs only the CWD into
`.../eqr_run_<ts>/` and builds `//<stagedir>:main`, destroying the
authoring-time google3 module path. A hardcoded absolute import
(`from google3.<original.pkg.path> import sibling`) or cross-package BUILD
`dep`/`data` label names something ABSENT from the staged binary: the worker
dies at import, before `main()`, no marker, behind the log wall. It builds
locally: that package is present.

Use the EqR-jax `eqr_run_*` idiom:
`sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))` in the entry
point, siblings imported by BARE name. Sibling `.py` ride along in a BUILD
`data` glob (`strict_deps = False`), relative SYMLINKS to one source of truth,
no drift; `rsync -aL` gives real files. `from . import x` fails: a
`py_binary` main runs as `__main__`, no parent package. Verify: build
`//<a-renamed-throwaway-dir>:main` without the sibling package, then `--help`.
In-place testing proves nothing.

Three signs diagnose a pre-`main()` death: empty status message, no application
log anywhere including mirrors, no surviving job handle. Do not re-launch for
impossible logs. Check quota first: an over-quota cell looks identical after
hours, log created, first write refused. A 0-byte log means never started or
unable to write; artifacts timestamped long after launch settle which
(`../storage.md` §An Over-Quota Cell Looks Like A Broken Program).

Getting logs, most reliable first:

| Source | Caveat |
|---|---|
| Staged binary run locally: try FIRST | Covers most import and startup failures. The staged per-run SNAPSHOT (`.../eqr_run_<ts>_<hash>/`) ran, not your edited workspace, so workspace line numbers can describe a file never run. It carries a `BUILD`: `blaze build <snapshot_path>:main`, job's argv, ~40 s, zero credits. Answers what probe launches and log instruments cannot: flag arrival, torch load, beacon fire, startup latency. |
| Work unit job state: cell, user, job name, task counts, status message | Request detailed status explicitly, or it returns silently empty, like a gone job. Garbage-collected in minutes; the status message lasts far longer, usually with the exception. |
| App log mirrored to durable storage, teed from program start, flushed on error lines | Outlives task, work unit, and experiment; covers only post-start failures. Often Borg's only log, so protect it (`../engineering.md`: handlers steal streams). |
| Log-tailing CLI | Works sometimes. |
| Log-search CLI | May be blocked by workstation permissions. |

Restricted-LOAS walls off EVERY worker-log service: from a workstation
credential, `borg tasklog`, `analog --remote`, and the F1/`get_job` path can
all return `PERMISSION_DENIED` (`borg tasklog` SIGABRTs on it), so stop after
the first. Write diagnostics to the destination, read with `fileutil`: a
numbered startup marker as the FIRST action in `main()`, one per stage, plus a
`try/except` dumping the traceback to CNS. Per `../storage.md` §"write a copy's
evidence to the destination, not to a log".

That marker splits two look-alike deaths. `VMGROUP_STATE_RUN`, empty status,
zero output, no readable log is NOT necessarily a pre-`main()` death, only one
you cannot see. Present: reached `main()`, cause downstream. Absent: death
before logging, or an over-quota cell refused the first write (`../storage.md`).

Two failure modes fire only remotely, past a green build and smoke test. First,
standard-library file APIs on a distributed path (`liveness.md` §Identity,
Paths, And Local Disk On A Worker). Second, mocked third-party libraries, the build stubbing some
externals (`../engineering.md` §Failure Modes That Only Appear On The Long Path).

## Launcher-Side Failures That Look Like Scheduler Failures

**A job that never created a work unit, or a launch that produced no XID, never
reached the scheduler.** Such submit-path failures are workstation-local, not
allocator or quota rejections.

- Never pipe into the submit command; background launches take stdin from
  `/dev/null`. Attribution prompts need only EOF, supplied by `< /dev/null`;
  piping `yes` segfaults the CLI, no XID, no diagnostic. WITHOUT `< /dev/null`,
  `nohup`/`setsid` reads EOF, re-loops, SUBMITS AGAIN: one `tpu queue` gives
  TWO experiments on one out_dir (two writers = corruption), while
  `~/.tpu_jobs.json` records one, leaving the survivor unregistered. Launch
  `tpu queue ... < /dev/null`; confirm EXACTLY ONE experiment with
  `"$XM" list --experiment_name=<name>`, rc captured. Never bare
  `xmanager.par ... | grep` (§Checking Whether One XID Is Still Alive:
  unresolved binary + pipeline reads like "no such job").
- No anti-dup wrapper killing the launcher on `Experiment id: N`. It prints at
  creation, BEFORE the blaze build (minutes) and any work unit; killing there
  leaves a RUNNING-forever zombie: experiment shell, "No work units found", no
  log dir, no out_dir. Only `Launched experiment N`, or on resume
  `Added N work unit(s) to experiment`, means finished; both print after the
  build and work-unit add. Retry on that line's ABSENCE, needing no kill logic
  under `< /dev/null`. Grep
  `Launched experiment|work unit\(s\) to experiment`, never `Experiment id:`.
- ANSI-strip output before grepping the XID. XManager colors it:
  `Launched experiment \e[1m\e[34m281839914\e[0m "name"`, so
  `Launched experiment \K\d+` matches nothing (ESC follows the space, not a
  digit) and a healthy job reads as "launch failed". Pipe through
  `sed 's/\x1b\[[0-9;]*m//g'` first. Likewise log-mirror step numbers and
  status: colored `SUBMITTED`/`Preempted.` have bitten watchers.
- A full `/tmp` breaks the submit with `SIGBUS`. `/tmp` is RAM-backed tmpfs, a
  repro's core dump fills it, the next writer dies on an unobtainable page.
  Disable repro cores, check free space first: every `/tmp` byte is RAM stolen
  from the machine doing cold imports.
- Bazel will not glob a package holding an absolute symlink ("Absolute symlinks
  are forbidden"). Dereference when copying a checkout that symlinks the shared
  launcher in. The package glob cache keeps that rejection: fixing the tree is
  not enough, restart the build server.
- The launcher forwards flags as a `key=value` dict the binary must accept.
  `--app.<flag>=<v>` passes one flag verbatim, but positionals are
  inexpressible and `store_true` arrives as `--flag=`, rejected by argparse.
  Both kill every task in parsing, before logging, and an unlimited restart
  budget churns forever writing nothing, like a scheduler problem. Select
  subcommands with a valued flag, booleans with explicit values.
- A flag must handle BOTH "absent" and "present but empty". A default of `""`
  collapses them: passed, parsed empty, default branch taken, fleet silently in
  the wrong mode. Default to `None`; test all spellings.
- Record each task's identity and mode somewhere readable: when tasks never log,
  a startup marker on distributed storage may be the only diagnostic.
  `$BORG_TASK_INDEX` is never set by XManager, so use the BCL `%task%` macro.

## Metrics And Curves

There is no external experiment tracker here. The internal equivalent stores
scalars in a table service and plots them in a dashboard service, both keyed by
experiment id. `../research/result_logging.md` owns the URL forms, how to verify a
run actually wrote metrics, and the settings that are easy to get wrong
(explicit opt-in, rank-0 only, periodic flush). **Reading the curves back from
the workstation is possible and has three routes, bucket first:**
`../research/result_logging.md` §Reading The Curves From The Workstation. A
report that says "the workstation cannot read the datatable" has skipped them.

Current wrapper code, allocator configuration, work-unit state, and logs outrank
this guide whenever implementation details change.

