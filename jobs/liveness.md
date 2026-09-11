# Preemption, Liveness, And The Worker Environment

Surviving preemption with the right restart budget, telling a live job from a
dead one that still reads `state: RUN`, where the storage CLI does and does not
exist, and the identity / path / local-disk rules a worker runs under. Part of
the `jobs/` set; the hub is `../jobs.md`.

## Preemption, Restart, And Resume

- **A restart restores nothing.** The binary re-executes from the top on a fresh
  machine, same arguments. No process state, memory image, accelerator snapshot
  or execution position survives, only application checkpoints.
- Without a restart budget the first preemption is fatal. Set an explicit
  scheduling policy: unlimited task failures, one per task per credit window.
  Long runs then survive unrelated preemptions, and a repeat offender is declared
  dead, not retried forever.
- In a preemption STORM (thin/borrowed capacity, no floor) the default
  `borg_max_per_task_failures=1` kills a job merely holding ground. It is not a
  never-restart setting. `xm_launcher.py` defaults: `borg_max_task_failures=-1`
  and `borg_max_task_evictions=-1`, both unlimited, plus
  `borg_max_per_task_failures=1` on a 7200s credit window. A clean preemption is
  an eviction, harmless against an unlimited budget. A torn-apart gang leaves
  survivors exiting non-zero, a per-task failure. With no floor, repeated ABORTs
  burn each task's one credit inside one 7200s window and the job flips to FAILED
  (`task_states=[ABORT×N, FAILURE×k]`, WU=FAILED): observed killing several
  no-floor v4-256 arms repeatedly. Ride out a storm on
  `tpu queue ... --borg_max_per_task_failures=100`, evictions unlimited: ABORTs
  re-queue instead of failing the job. Waiting is never fatal: a never-scheduled
  job is NEVER failed for it, and the board routinely shows others pending 2d+.
  Only schedule-then-abort on an exhausted budget dies. A real floor beats this
  knob, a borrowed-capacity stopgap (see the survival test above).
- Keep checkpoints out of the working directory: task-local, wiped by the event
  the budget exists to survive. Without them the budget buys only a step-zero
  rerun.
- A task walking a fixed list never revisits a passed index. Preempt the tail and
  the job stays `running`: slot held, healthy, nothing emitted. Gate on finished
  units, not liveness. Act on a stalled count. Two corpora each stopped a handful
  of units short, so finish tails by other means.
- Size a work unit against the preemption window, not convenience. A unit longer
  than the mean uninterrupted window never completes and fails silently: every
  task busy, nothing emitted, no error. A ~6-minute window against a 195-minute
  shard never finishes and looks healthy. Re-slicing to minutes is free when work
  is a pure function of its index.
- Two launcher settings. Open log-read access, sparing an ACL dance. No
  interconnect-resilient slice for accelerator jobs: resilience costs roughly a
  third of throughput, and rescheduling onto a healthy slice beats finishing much
  slower.
- A restart loop proves neither a crash nor slowness. A training loop producing
  zero steps exits 0 and restarts forever, logging only successes. Use the
  kill-versus-exit tests in `../engineering.md` before blaming infrastructure.
  Verify a resume by step progress, never exit status.

Resuming is not pointing at a checkpoint. The resume flag appends a work unit to
an existing experiment. The prefix comes from the experiment id, so the attempt
lands there and auto-resume picks the newest complete checkpoint. The launcher
must not also pass an explicit load path. Auto-resume yields to explicit
requests, and only the job knows which step finished writing. A guess disables it
with an unusable path. Reserve explicit paths for external checkpoints, at a
concrete step directory.

A resume re-runs the ORIGINAL snapshot, immutable and prebuilt, never the current
checkout, which drifts within days. Package the working tree and the checkpoint
resumes into code it never saw. The newer validator refuses retired config keys,
killing the run's own config at flag-parse time, a packaging round wasted. A new
default adding or renaming a module leaves the checkpoint unrestorable, surfacing
minutes in as a model mismatch. Re-run the stagedir from the job registry.
Missing or unknown is an error, never a cue to package what is here now.
Deliberate changes belong in a new experiment: a resume records nothing about
code changing.

Auto-resume belongs in the application, in-process at startup. Read the
checkpoint prefix, skip an explicit load or an eval-only run, and enumerate step
directories. Ignore any without the last-written marker file, whose absence means
an interrupted write. Resume from the highest surviving step. Enumerating the
prefix beats parsing logs, which a rotation restarts from zero.

## Where The Storage CLI Exists, And Where It Does Not

**The storage command-line tool is on the workstation and NOT inside a job
container**, which decides where a data-movement job should run.

A container ships the path-library client and nothing else, so shelling out to
the CLI there does not fail loudly. It hangs until the timeout with no output,
in state `RUN`, with nothing in the termination records because nothing
terminated. Two assembly jobs burned half an hour each that way.

This is more than "handle both backends". Server-side concatenation and
cross-cell copy exist only on the workstation path; in a container the same
operation carries every byte through the task. A tens-of-GB copy therefore
cannot finish inside a preemption window on the cluster, but finishes
comfortably from a workstation (not preemptible, acting only as a controller).
Probe which backend is live at runtime and branch. Keep a local branch too, or
the code is untestable off distributed storage, where the last several bugs in
ours survived.

## `state: RUN` Is Not Evidence That Anything Runs

**Check the VM-group states, not the job state.** A job reads `state: "RUN"`
for hours, all groups in `ASSIGN`/`PENDING`:

```
borg --borg=<cell> findjobs --name_re="<user>_group_<XID>\..*" \
  | grep -oE "VMGROUP_STATE_[A-Z]+"
```

No `VMGROUP_STATE_RUN` means nothing runs, whatever the job says.

Judge liveness by artifacts, not status queries. One run hung mid-epoch: no
crash, NCCL error, rank exit or new attempt. For 17 frozen minutes XM
`cancel --dry-run` said `RUNNING`, `tpu queue-status` `SUBMITTED`, both wrong.
(`borg findjobs` was empty, but that is not a third source: `--user=<me>` is
not a valid flag and returns empty rather than erroring, so an empty result
there means nothing unless you used `--user_re=` or `--name_re=`;
`../engineering.md` §Verify The Premise Before Changing Anything.)
Frozen: log mirror, newest checkpoint `mtime`, step counter. Hangs are
invisible to grep; watchers need a stall probe on step numbers minutes apart.

Read every rank's newest attempt, not one log file; each qualifier fails alone.
A watcher pinned to `rank_0_attempt1.log` read "step 8097, no change" three
times while training ran on `attempt3`. Refitted to the newest, it froze on a
post-requeue dead XID.

| qualifier | what it defends against |
|---|---|
| every rank, not rank 0 | rank 0 exits while peers write, or the reverse |
| newest attempt each poll | preemption starts `attempt<N+1>`; old files read |
| artifact, not status query | XM and the queue report a dead job an hour |

The checkpoint directory is the strongest probe, independent of the log path.
No new `step_<N>` past one known wall-clock interval is a verdict, not a hint:
45 minutes without `step_10240` at a 1024-step cadence, XM still `RUNNING`.

XM state is unusable for liveness, not merely delayed; never bound its
staleness. The 17-minute case reads as lag. XM later said `RUNNING` 63 minutes
past a job's last byte, queue stuck at `SUBMITTED`. Another XID in that batch
showed `NOT_RUNNING`: tool fine, record wrong. Two lines hit that pair in one
night.

The scheduling ceiling sits far below the advertised quota. On the shared CPU
pool, fan-outs totaling several hundred GiB of RAM sat unscheduled for hours;
a fraction of that size reached RUN in seconds. Size fan-outs against what
schedules, using the command above.

Launcher hygiene, each having cost a launch:

- An XID is not a job: launchers print normal-looking ones for jobs that never
  scheduled. Confirm at the cluster layer.
- Truncate a launcher log before scraping: its last "Launched experiment" line
  may be a killed attempt's, naming a nonexistent job.
- Stop takes the experiment flag, not a positional or an abbreviated one.
- A jobs-board entry outlives the experiment: `PENDING` 21 hours after it
  reports "not found". Archive them, they are not work.
- A killed launcher tool-call does not stop the launch: a detached/`setsid`
  submit outlives its shell, so relaunching double-submits. Check the results
  file and `tpu check` first.
- Alive-but-wedged: board `running`, logs frozen, no restart. It started,
  unlike the unscheduled case, then hung mid-startup, classically at
  `Downloading dataset ...` staging the ~69G Maze mirror into `/tmp`. The Borg
  task lives, the process inside stuck: `running`, `1 active` WU, no new log
  lines, no `attemptN+1`. Borg restarts only dead tasks, so nothing trips the
  watchdog and the PROD slot burns indefinitely. Diagnose by newest log mtime
  against wall clock: >30 min of zero growth on all ranks, against a normal
  ~5 min download, is wedged, not slow. A sibling reading the same path fine,
  `step_*` ckpts advancing, blames these workers, not the data. Fix:
  `tpu cancel <xid>`, relaunch the validated config; fresh placement usually
  clears it. Verify `step>0`: the bug can re-roll onto another bad node.

## Identity, Paths, And Local Disk On A Worker

- **A cluster job is a different security principal from you.** Nothing you read
  interactively is automatically readable from a worker, and the same wall
  blocks log mirroring to a personal bucket. The cheapest fix is the internal
  distributed filesystem, which the job identity reads and writes natively,
  usually a one-line path change. Otherwise a bucket owner must grant the job's
  principal access; an org-level deny policy can block even owners, and
  service-account keys are not an option.
- The temporary directory is a RAM disk you must size yourself. The default is
  small and every task stages its own private copy of what it downloads, so an
  undersized value surfaces mid-run as "no space left on device". A job moving
  large files should stream through a bounded buffer instead.
- The RAM disk and the memory limit are two different knobs the launcher must
  pass explicitly; sizing `/tmp` does nothing for a process that allocates.
  Watch for a resource that must be named in its own field: appended to the
  accelerator string it reads as a second accelerator, accepted and ignored.
- Shell file utilities do not exist inside the container, and the standard
  library breaks on a distributed path or remote URI. `os.path` raises a
  permission error or silently answers False, a bucket URI fails a directory
  check, and normalization mangles the URI. That is how a valid remote load
  path becomes a bogus "does not exist". Route every existence check and remote
  read through the project's path helpers. This survives a green build and a
  local smoke test, because it only fires remotely.
- The launcher-to-application contract travels as environment variables, not
  config flags: the external checkpoint to load, the tracking run to continue,
  and the durable checkpoint prefix. That prefix derives from the experiment id,
  so every restart resolves to the same location, which is what makes in-process
  auto-resume well defined. Do not inject a checkpoint path as a config flag if
  the config schema is locked; every job dies at startup.

