# Preemption, Liveness, And The Worker Environment

Surviving preemption with the right restart budget, telling a live job from a
dead one that still reads `state: RUN`, and the identity / path / disk rules a
worker runs under. Chapter 1 is the principles, Chapter 2 how to check liveness,
Chapter 3 the classic bugs. Part of the `jobs/` set; the hub is `../jobs.md`.
Siblings: `submit.md`, `resume.md`, `diagnose.md`, `report.md`.

---

## Chapter 1 — Principles

### Preemption, Restart, And Resume

**A restart restores nothing: the binary re-executes from the top on a fresh
machine with the same arguments, and only application checkpoints survive** — no
process state, memory image, accelerator snapshot, or execution position. So keep
checkpoints OUT of the working directory (task-local, wiped by the very event the
budget exists to survive), or the budget buys only a step-zero rerun.

- Set an explicit restart budget, or the first preemption is fatal. `xm_launcher.py`
  defaults `borg_max_task_failures=-1` and `borg_max_task_evictions=-1` (both
  unlimited) plus `borg_max_per_task_failures=1` on a 7200s credit window. A clean
  preemption is an eviction, harmless against an unlimited budget; a torn-apart
  gang leaves survivors exiting non-zero, a per-task failure; a repeat offender is
  declared dead, not retried forever.
- In a preemption STORM `borg_max_per_task_failures=1` kills a job merely holding
  ground — it is not a never-restart setting. With no floor, repeated ABORTs burn
  each task's one credit inside one 7200s window and the job flips to FAILED
  (`task_states=[ABORT×N, FAILURE×k]`, WU=FAILED; seen killing no-floor v4-256 arms
  repeatedly). Ride it out on `tpu queue ... --borg_max_per_task_failures=100`,
  evictions unlimited, so ABORTs re-queue instead of failing the job; a real floor
  beats this stopgap.
- Waiting is never fatal: a never-scheduled job is NEVER failed for it (others
  routinely pend 2d+); only schedule-then-abort on an exhausted budget dies.
- Gate on finished units, not liveness: a task walking a fixed list never revisits
  a passed index, so preempting the tail leaves the job `running` — slot held,
  nothing emitted. Act on a stalled count, and finish tails by other means.
- Size a work unit against the preemption window, not convenience: a unit longer
  than the mean uninterrupted window never completes and fails silently (a
  ~6-minute window against a 195-minute shard). Re-slicing to minutes is free when
  work is a pure function of its index.
- A restart loop proves neither a crash nor slowness: a training loop producing
  zero steps exits 0 and restarts forever, logging only successes. Verify a resume
  by step progress, never exit status; use the kill-versus-exit tests in
  `../engineering.md` first.
- Two launcher settings, each cheap: open log-read access (sparing an ACL dance),
  and NO interconnect-resilient slice for accelerator jobs (resilience costs
  roughly a third of throughput; rescheduling onto a healthy slice beats finishing
  much slower).

Resuming is not pointing at a checkpoint. The resume flag appends a work unit to
the existing experiment, and the prefix comes from the experiment id, so the
attempt lands there and auto-resume picks the newest complete checkpoint. The
launcher must NOT also pass an explicit load path (auto-resume yields to explicit
requests, and a guess disables it with an unusable path); reserve explicit paths
for external checkpoints, at a concrete step directory.

A resume re-runs the ORIGINAL snapshot, immutable and prebuilt, never the current
checkout, which drifts within days. Re-run the stagedir from the job registry;
packaging the working tree resumes the checkpoint into code it never saw — the
newer validator refuses retired config keys and kills the run at flag-parse time,
or a renamed module leaves the checkpoint unrestorable minutes in as a model
mismatch. Missing or unknown is an error, never a cue to package what is here now;
deliberate code changes belong in a new experiment.

Auto-resume belongs in the application, in-process at startup: read the checkpoint
prefix, skip it for an explicit load or an eval-only run, enumerate step
directories, ignore any without the last-written marker file (its absence means an
interrupted write), and resume from the highest surviving step. Enumerating the
prefix beats parsing logs, which a rotation restarts from zero.

### Where The Storage CLI Exists, And Where It Does Not

**The storage command-line tool is on the workstation and NOT inside a job
container**, which decides where a data-movement job should run. A container ships
the path-library client and nothing else, so shelling out to the CLI there does
not fail loudly: it hangs until the timeout with no output, in state `RUN`, with
nothing in the termination records because nothing terminated (two assembly jobs
burned half an hour each that way).

This is more than "handle both backends". Server-side concatenation and
cross-cell copy exist only on the workstation path; in a container the same
operation carries every byte through the task, so a tens-of-GB copy cannot finish
inside a preemption window on the cluster but finishes comfortably from a
workstation (not preemptible, acting only as a controller). Probe which backend is
live at runtime and branch, and keep a local branch too, or the code is
untestable off distributed storage.

### Identity, Paths, And Local Disk On A Worker

**A cluster job is a different security principal from you:** nothing you read
interactively is automatically readable from a worker, and the same wall blocks
log mirroring to a personal bucket. The cheapest fix is the internal distributed
filesystem, which the job identity reads and writes natively (usually a one-line
path change); otherwise a bucket owner must grant the job's principal access — an
org-level deny policy can block even owners, and service-account keys are not an
option.

- The temporary directory is a RAM disk you must size yourself: the default is
  small and every task stages its own private copy of what it downloads, so an
  undersized value surfaces mid-run as "no space left on device". A job moving
  large files should stream through a bounded buffer instead.
- The RAM disk and the memory limit are two different knobs the launcher must pass
  explicitly; sizing `/tmp` does nothing for a process that allocates. A resource
  appended to the accelerator string reads as a second accelerator, accepted and
  ignored — name it in its own field.
- Route every existence check and remote read through the project's path helpers:
  shell file utilities do not exist in the container, and the standard library
  breaks on a distributed path or remote URI (`os.path` raises a permission error
  or silently answers False, a bucket URI fails a directory check, normalization
  mangles the URI), so a valid remote load path becomes a bogus "does not exist".
  This survives a green build and a local smoke test because it only fires
  remotely.
- The launcher-to-application contract travels as environment variables, not config
  flags: the external checkpoint to load, the tracking run to continue, and the
  durable checkpoint prefix (derived from the experiment id, so every restart
  resolves to the same location — what makes in-process auto-resume well defined).
  Do not inject a checkpoint path as a config flag if the schema is locked; every
  job dies at startup.

---

## Chapter 2 — Checking Liveness

### `state: RUN` Is Not Evidence That Anything Runs

**Check the VM-group states, not the job state.** A job reads `state: "RUN"` for
hours with all groups in `ASSIGN`/`PENDING`; no `VMGROUP_STATE_RUN` means nothing
runs, whatever the job says.

```
borg --borg=<cell> findjobs --name_re="<user>_group_<XID>\..*" \
  | grep -oE "VMGROUP_STATE_[A-Z]+"
```

Then judge liveness by artifacts, not status queries — the log mirror, newest
checkpoint `mtime`, step counter. Hangs are invisible to grep, so a watcher needs
a stall probe on step numbers minutes apart; one run hung mid-epoch (no crash,
NCCL error, rank exit, or new attempt) while for 17 minutes `cancel --dry-run`
said `RUNNING` and `tpu queue-status` `SUBMITTED`, both wrong. (`borg findjobs`
was empty, but `--user=<me>` is not a valid flag and returns empty rather than
erroring, so empty means nothing unless you used `--user_re=` or `--name_re=`;
`../engineering.md` §Trust artifacts, not success returns.)

Read every rank's newest attempt, not one log file — each qualifier below fails
alone (a watcher pinned to `rank_0_attempt1.log` read "step 8097, no change" three
times while training ran on `attempt3`):

| qualifier | what it defends against |
|---|---|
| every rank, not rank 0 | rank 0 exits while peers write, or the reverse |
| newest attempt each poll | preemption starts `attempt<N+1>`; old files read |
| artifact, not status query | XM and the queue report a dead job an hour |

The checkpoint directory is the strongest probe, independent of the log path: no
new `step_<N>` past one known wall-clock interval is a verdict, not a hint (45
minutes without `step_10240` at a 1024-step cadence, XM still `RUNNING`). XM state
is unusable for liveness, not merely delayed; never bound its staleness — it said
`RUNNING` 63 minutes past a job's last byte with the queue stuck at `SUBMITTED`,
while another XID in that batch showed `NOT_RUNNING` (tool fine, record wrong).

The scheduling ceiling sits far below the advertised quota: on the shared CPU
pool, fan-outs totaling several hundred GiB of RAM sat unscheduled for hours while
a fraction of that size reached RUN in seconds. Size fan-outs against what
schedules, using the command above.

---

## Chapter 3 — Classic Bugs And What To Do

### Launcher hygiene

Each row has cost a launch.

| Symptom | Cause | Fix |
|---|---|---|
| An XID for a job that never scheduled | launchers print normal-looking XIDs regardless | an XID is not a job; confirm at the cluster layer |
| "Launched experiment" names a nonexistent job | the log's last such line may be a killed attempt's | truncate the launcher log before scraping |
| `stop` does nothing | it takes the experiment FLAG, not a positional or an abbreviated one | pass the experiment flag |
| A board entry `PENDING` 21 h after it reports "not found" | a jobs-board entry outlives the experiment | archive them; they are not work |
| Relaunching double-submits | a killed launcher tool-call does not stop the launch; a detached/`setsid` submit outlives its shell | check the results file and `tpu check` first |

### Alive-but-wedged

**Board `running`, logs frozen, no restart: the task started (unlike the
unscheduled case) then hung mid-startup**, classically at `Downloading dataset ...`
staging the ~69G Maze mirror into `/tmp`. The Borg task lives and the process
inside is stuck: `running`, `1 active` WU, no new log lines, no `attemptN+1`; Borg
restarts only dead tasks, so nothing trips the watchdog and the PROD slot burns
indefinitely. Diagnose by newest log `mtime` against wall clock: >30 min of zero
growth on all ranks, against a normal ~5 min download, is wedged, not slow (a
sibling reading the same path fine, `step_*` ckpts advancing, blames these
workers, not the data). Fix: `tpu cancel <xid>`, relaunch the validated config;
fresh placement usually clears it, but verify `step>0` — the bug can re-roll onto
another bad node.
