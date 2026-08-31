# Engineering Discipline

Read this before changing code, diagnosing a failure, or reporting a result, in
any checkout. It owns METHOD: the habits that are expensive to relearn.
`projects/` owns each codebase's semantics; `jobs.md` and `storage.md` own
infrastructure.

## Verify The Premise Before Changing Anything

- **Reproduce first.** Inspect the relevant code, tests, and recent history, and
  compare current behavior against the acceptance criteria. "No change needed"
  is a valid outcome. A failed reproduction is not proof, though: an earlier
  partial fix produces the same silence.
- **Prove the smallest thing that can fail, locally, before paying for a remote
  round trip.**
- **A green build proves the code compiles, not that it works.** Under relaxed
  dependency checking a missing import is a runtime error on the remote machine.
  Run the artifact. Importing the whole graph (a `--help` invocation) costs
  seconds and catches the entire "died before `main()`" class.
- **A CLI can reject your flag and still exit 0, so read the OUTPUT of a
  state-changing command, not just its `rc`.** `xmanager stop --xid=<id>` prints
  `unrecognized arguments` and returns 0, doing nothing. `borg findjobs
  --user=<me>` does the same and reads as "you have no jobs in this cell"; two
  different tools, one shift. The transcript looks like success, so the next
  sentence you write is "stopped it". For anything destructive, prefer a CLI's
  own `--dry_run` and confirm the blast radius (how many objects matched, and
  that the ones you must NOT touch are absent) before the real call. Then close
  the loop on the target's own artifacts, not on `rc`.
- **Before claiming completion**, re-read the original request, run the most
  relevant checks, read their COMPLETE output, and compare the result against
  the request rather than against your patch. State whatever remains unverified.

## Debug Locally On CPU Before You Spend A Remote Round Trip

**After any large code change, run the whole path on CPU with a `local_debug`
config before submitting a job.** A remote round trip costs a build, a queue
wait, a schedule and a stagedir; a CPU run costs a couple of minutes and catches
most of what would have died on the accelerator. Five consecutive TPU launches
on one line were burned on bugs a workstation would have found in two minutes.

Each repo carries the runner: `scripts/local_debug.sh` (some repos put it at the
root; `tpu_scripts/debug.sh` is the older shape of the same idea). Read the one
in your checkout before writing anything new. The mechanism is two parts:

| Part | What it does |
|---|---|
| Force CPU with an env var | `JAX_PLATFORMS=cpu` for JAX. Set it before `import jax`; it cannot be set afterwards. Pair it with `XLA_FLAGS=--xla_force_host_platform_device_count=N` to simulate N chips in one process, so sharding and per-device code run too |
| Point the binary at a `local_debug` config | `--config=configs/load_config.py:local_debug`. It shrinks steps, batch and data so the run finishes in minutes, and keeps every stage the real config has |

**Cover the side paths, not just the training step, because they are where the
remote-only bugs live.** Logging, visualization, checkpoint save and restore,
and both online and offline eval each need to execute in the local run. A step
loop that trains fine and then dies at the first checkpoint has cost the whole
launch. Concretely, these fire only when the code actually runs:

- A stubbed library raises at CALL time, not import time, so a wandb or plotting
  stub only fails at the first log or figure, thousands of steps in.
- A checkpoint save is a multi-host collective; if non-chief ranks skip it, the
  job HANGS rather than failing. Run `--procs 2` where the script supports it,
  because a single process cannot exercise a barrier.
- Distributed paths need a timeout. A deadlock produces no traceback, so an
  untimed smoke hangs and proves nothing; the EqR runner uses 300s, about 6x its
  healthy runtime.
- `/cns` paths reject stdlib file APIs, and eval or checkpoint code is usually
  where a plain `open()` survives review.

**Make the local run a positive test.** Print a token like `LOCAL_DEBUG_OK` on
the last line and check for it, rather than trusting the exit code: a piped
runner reports the last stage's status (§Verify The Premise Before Changing
Anything), and a timeout kills the wrapper, not the child. If a dependency the
test needs is unreachable, say so loudly rather than skipping it, or the run
passes while proving nothing (§A Test That Cannot Fail).

Then, and only then, do the remote debug run. Keep it small and treat it as a
separate step: it exists to catch what CPU cannot see (real accelerator
topology, cross-host collectives at true scale, the launcher's own argv and
staging), not to re-find what the local run already covers.

## Diagnose From Evidence, Not From The Most Available Story

- **Read the deepest relevant failure, not the last line.** A traceback string
  alone is not a code bug: check for an earlier OOM, an environment error, or a
  swallowed exception upstream.
- **Distinguish "it was killed" from "it exited".** Different footprints (exit
  codes, attempt identity, failure counters, any shutdown marker the program
  writes itself) and opposite fixes.
- **A log's last LINE is not proof of life; its last WRITE TIME is.** A remote
  job's log persists after the job is preempted or dies, so the final `[step
  N/T]` reports where it STOPPED, not where it IS. Re-reading the same static
  file confirms the stale number and reads as "healthy, unchanged" when it means
  "dead": a monitor reported a run "healthy ~11%" three times off a log whose
  mtime was two hours old, preempted at that step. Check the log's mtime
  (`fileutil ls -l`) against now, or read authoritative scheduler state (`tpu
  check` / borg BCL), never the log body alone. Not advanced AND mtime older
  than a few minutes = preempted.
- **A cause that does not move when the suspect moves is not the cause.**
  Correlate the symptom's period or magnitude with the thing you suspect before
  acting on it.
- **A serial pipeline does not bound memory; standing servers do.** Each
  workspace's blaze server holds a multi-GB JVM heap for its whole
  `max_idle_secs`, one per checkout, whether or not a build runs.
  `learning/deepmind/config/blazerc` sets that to **7 days** with an 18G heap and
  leans on `--shutdown_on_low_sys_mem`, which only fires once memory is already
  tight and whose eviction cold-respawns the heap, deepening the dip. Enumerate
  resident heaps (`ps` by RSS plus `VmSwap`; a swapped-out heap reads as small in
  RSS yet still owns the pages) before blaming concurrent builds. Bound it in
  `~/.blazerc` after the DeepMind `import` (last startup flag wins). That binds
  only NEW servers, so pre-existing ones need one sweep;
  `~/work/.monitor_watch/blaze_reaper.sh` is that sweep. A capped
  `max_idle_secs` is not self-enforcing: `blaze shutdown` can return rc=0 with no
  output and leave the server running (seen on a server whose lock holder had
  died), so a reaper must escalate to signals and confirm the pid is gone.
- **A cron job's `flock` fd is INHERITED by any blaze server it spawns, so the
  lock is held for the server's whole `max_idle_secs`, not the script's run.**
  A `*/5` cron then fires once per idle window instead (measured 61.9min against
  `max_idle_secs=3600`), and writes no log line at all: the script is never
  exec'd, so "no errors in the log" is the symptom, not the refutation. Judge by
  the interval between log entries, and read the holder
  with `readlink /proc/<pid>/fd/*`, because `fuser` measured empty on a held flock. Fix it
  with `flock -n -o` in the crontab line (`-o` closes the fd before exec; mutual
  exclusion during the command is unaffected), never by lowering
  `max_idle_secs`, which only shortens the hostage. One line, verified: the
  61.9min cluster went 18 occurrences -> 0 across the next 2.3h, and the
  freshness alarm it fed went 31/day -> 0.
- **`timeout` kills the blaze CLIENT; the SERVER builds on and often SUCCEEDS,
  so a nonzero exit code can describe a build that produced a good binary.**
  Measured: a fully cached build (7601/7602 actions cached) still took 1738s on a
  swapping host, and blaze logged `Build completed successfully` after
  `timeout 900` had killed the client. A "done" stamp gated on that rc is never written,
  so the work re-fires forever (139 "refresh due" vs 17 "ok" in four days). Gate
  the stamp on the ARTIFACT, not the rc, size the timeout for a cold build on a
  loaded host, and capture `rc=$?` on the very next line; any intervening
  statement resets it.
- **Judge a server idle by the artifact a build writes, not by the process.**
  `command*.profile.gz` mtime in the `output_base` is one-per-command and is the
  judgement that works. Two plausible substitutes are actively dangerous. A
  missing `blaze_build_log`/`command.log` (absent in 6 of 7 output_bases) stats
  as epoch 0 and reads as maximally idle, which reaps every server including
  live ones. And CPU-time delta is never zero (GC and heartbeat threads) and is
  highest on the fattest idle heap, inverting the ranking it is meant to
  produce. Guard on top of the judgement (no children, lock holder dead) and
  make a missing artifact fall back to something conservative.
- **Two broken things can be true at once.** A real, measurable problem standing
  next to the failure is not automatically its explanation.
- **Absence of evidence is evidence.** No log, no status message, and no
  surviving handle together mean the failure happened before logging existed.
  Do not re-run to collect logs that cannot exist.

## When A Result Is Rejected, Change The PREDICATE, Not The Command

**A correction re-runs the measurement; it does not fix a broken way of reading
it.** Told that a survey was wrong, the reflex is to re-issue it with a more
thorough command (`ls -d` becomes `ls -l`) while the line that turns output into
a verdict is copied across unchanged. The second run is then just as wrong as
the first, and now it carries the authority of having been double-checked.
Re-derive the verdict, not the data: state what would have to be true for the
old reading to be wrong, and check that.

Two failure shapes hide behind an identical re-run, and both survive a more
careful command:

| what was actually wrong | why re-running does not catch it |
|---|---|
| the **predicate** (grep on text that both outcomes contain) | any command feeding it produces the same verdict |
| the **subject** (probing the wrong path, the wrong tree, `git show HEAD:f` instead of the worktree) | the reading is correct, but of the wrong object |

The second is the quieter one: in a dirty worktree, the committed file and the
file on disk are different objects, so a report built from `HEAD` can describe
work that was finished hours ago as still outstanding. Name the object you
measured in the finding itself ("in the worktree", "at HEAD"), because the
sentence is what gets relayed, and by then nobody can tell which one you read.

## A Test That Cannot Fail Proves Nothing — And Often Finds The Bug

**Write the negative control before believing a checker**, and prefer a test
over another hour of reading logs.

A verifier only ever run against good data is untested; `storage.md` records a
mirror check that compared a constant against itself and passed against a
nonexistent destination. So for every checker, break exactly one property
(truncate the payload, duplicate a key, shorten an index array, flip one byte
while keeping the length) and require the verdict to flip.

A negative control proves the property it exercised, not the artifact you will
act on. A memory-wall smoke script injected the fault correctly, was killed by
the cgroup, and wrote `SMOKE_RC=137` to its log, and still exited `rc=0`: the
inner status was captured for the log but never became the script's own exit
code. Every reading was true, but the one a caller would gate on
(`smoke.sh && echo OK`) was green at the exact moment the wall fired. Name the artifact the
next reader will actually consume (an exit code, a file, a counter) and assert
on that one, not on the nearest thing that moved. The author had caught the
identical shape ("the refusal path returned rc=0") in a different file an hour
earlier: checking the file you just edited is not the same as checking the
behaviour you depend on.

The fault you inject is itself a measurement. Two hours of log-reading on four
identical failures yielded only a plausible story ("storage flaky under
concurrency"); the retry test took minutes and made the real cause obvious. The
injected fault left the destination smaller than the boundary, an append cannot
shrink a file, so another process was writing.

Corollaries worth the line:

- **Report a violation as a verdict, not an exception**, where one bad item
  would otherwise abort the whole report and hide every other finding.
- **Keep the slow, obvious implementation** when you optimise a reader, and
  assert the fast one equals it. Batching reads reorders results, and scoring
  row A's label against row B's board looks entirely plausible.
- **A test written against a name that does not exist is the test working.**
  That drift between a config and the table it must agree with is exactly what
  it is there to catch.
- **When a reading and a reality can drift apart, put the freshness check
  INSIDE the reader.** A log file outlives the process that wrote it, so parsing
  one measures the past in a way that is indistinguishable from measuring the
  present. Make the accessor assert an age bound and raise, rather than return a
  stale value; cross-check the process table when the caller means "is it
  running". The worst version is a statistic over a frozen file: the same
  samples come back every call, so the variance collapses and the estimator
  reads as converged, and a shrinking error bar is the last symptom anyone
  suspects. Likewise a rate of zero from a dead lane must be an error, not the
  number 0, or it averages into an aggregate as if it were a measurement.
- **Before trusting a selector, force it to select, then force it to select
  everything.** A filter that reaps nothing and a filter that is simply broken
  produce the identical clean run, so "it touched nothing" is not evidence it
  discriminates. Run it once with the threshold slammed open and check the
  ranking is the one you meant: a judgement built on a missing file reads as
  maximally stale and selects the whole fleet, and one built on a proxy that
  grows with size (CPU burnt by a big GC heap) ranks the worst offender as the
  most active. Ask which way a missing or noisy input fails, and prefer the
  input whose absence fails closed.
- **Test the fix at a LARGER input than today's, never a smaller one.** A patch
  that only passes at the current size has not been tested. When a periodic job
  starts overrunning its period, the tempting proof is to shrink the input
  (prune the list, drop old rows) and re-measure: the number goes green while
  the slope is untouched, so the next item added re-breaks it and the regression
  reads as new. Fix the cost class instead (O(n) serial per-item RPCs become
  O(1) by fetching once and joining in memory) and demonstrate it by GROWING the
  input past the failure point, using synthetic rows on a COPY of the live file,
  never the live one. State the measured cost at 1x, 2x and ~3x the present
  size; a flat curve is the evidence, a single green run is not.

## Do Not Let A Diagnostic Kill The Thing It Watches

Guards, validators, and telemetry run inside the job but are not the job. Put
them behind a total comparison that can answer "can't tell", make them swallow
their own failures, and never let one raise into a training or serving loop. A
check that can crash a run has negative value.

**A monitor that hardcodes an endpoint reports a false mass-death when that
endpoint moves.** The amply UX gateway (the `:PORT` server behind the web UI and
cross-run query tools) has no stable port: on crash (e.g. LOAS2 expiry) it
relaunches on a fresh port and rewrites `~/.amply/dashboard_url`. Workers are
reparented to init and survive (verify `pgrep -af 'amply worker|claude-amply.py
resume'` + `ps -o ppid`: PPID=1 = independent of the gateway). A watcher
hardcoding the old port probes a dead socket and pages every session DEAD in one
second. Defenses: (1) read the base URL from `~/.amply/dashboard_url`, never
hardcode a port; (2) treat a simultaneous all-sessions DEAD with
`Connection refused` as gateway-down-until-proven, confirm workers alive first, and NEVER
`amp start`/kill a worker to "recover" (that is what kills a live session). The
gateway self-heals; repoint the observer, not the observed.

**While diagnosing a stuck healer, read its state; do not invoke it.** A probe
that runs the self-heal script (even `--help`) can trigger its side effect: a
rebuild whose `blaze` child outlives your `timeout` wrapper, orphaning to init
and joining the exact concurrent-build storm you are investigating. The
`timeout` kills the wrapper, not the grandchild it already forked. Inspect the
binary, the lock, and the logs directly; run the healer only once, deliberately,
after you understand the state, never as a way to observe it.

## A Guard's Threshold Is A Claim About Floats, Not About Algebra

I wrote a guard that fired on `spectral_radius >= 1.0`, then argued twice, in
two commit messages, that it could never fire, because
`rho = max(exp(-softplus(dt_bias) * exp(a_log)))` is `exp(-positive)` and so
strictly below 1. The algebra is correct. The guard fired anyway, at step 7586.

In fp32, `softplus(-30) = 9.4e-14`, and `exp(-9.4e-14)` rounds to exactly `1.0`
because fp32's eps is ~1.2e-7. Any exponent below that saturates. My own earlier
comment had even said "unreachable except through underflow": I wrote down the
exception and then reasoned as though it did not exist.

The general shape, which cost three wrong calls on one guard in one night:

1. `>= 1.0` can never fire (wrong: underflow) → changed it to fatal at 0.999
2. fatal at 0.999 is right (wrong: `rho` is a `torch.max` over 768 channels, so
   a high value names the slowest-decaying channel, not the model; the run at
   rho=0.9999 still had a fully intact depth ladder) → changed it to warn
3. 148 steps at a printed `1.0000` proves it cannot fire (wrong: it fired 11
   minutes later, because the printed value saturates at `%.4f` before the
   comparison does)

Two habits would have caught all three: evaluate the expression at extreme
inputs instead of reasoning about it (five lines of python showed the underflow
immediately), and check whether the statistic is a max, a mean, or a sample
before treating it as a property of the whole object.

## A Memory Cap Without A Swap Cap Is Not A Cap

`MemoryMax` alone does not stop a local job from taking the machine down, and it
fails in the direction that looks safe: the limit really is written into the
cgroup, `systemd-run` returns 0, and the process keeps running. Its semantics
simply exclude swap. On a box with 86G of swap, a job under an 8G wall can hold
8G of RAM plus tens of gigabytes of swap, and the frantic paging that produces
is itself what drives the memory-pressure signal. `systemd-oomd` kills on PSI,
not on a limit, so the wall is up and the bomb still goes off.

Measured on this workstation with a probe that really touches 521MB:

```
systemd-run --scope -p MemoryMax=64M                        → rc=0, probe alive
systemd-run --scope -p MemoryMax=64M -p MemorySwapMax=0     → rc=137, killed
```

The blast radius is the whole scope, not the offender. On 2026-08-30T20:07Z an
uncapped local eval reached 46.7G and oomd took out 31 processes in one tmux
scope: four unrelated agent lines and the operator's own amply server, all
restarted together. Nothing in that list had done anything wrong.

So the usable form is both knobs, always:

```bash
systemd-run --scope -p MemoryMax=8G -p MemorySwapMax=0 <cmd>
```

And put it behind a wrapper rather than trusting recall: `~/.tpu_bin/memcap`
takes `[-m LIMIT] <cmd...>`. A script heavy enough to matter should also REFUSE
to run uncapped: read `memory.max` and `memory.swap.max` from
`/proc/self/cgroup` and exit if either is unset, because the unsafe path is the
one that looks fine.

## Failure Modes That Only Appear On The Long Path

- **A short run does not validate resume.** Cold start and restore touch
  different data: a fresh tree holds arrays, a restored one also holds optimizer
  state whose leaves include `None`, scalars, and containers. Budget one
  deliberate restart before trusting a multi-hour schedule.
- **Code that runs every N steps fails N steps in.** Mocked or stubbed libraries
  raise at CALL time, not import time. Probe with `getattr` and degrade.
- **Anything that installs a handler can steal a stream someone else installed.**
  Verify the side effect after constructing logging, tracing, or writer objects
  rather than assuming composition.
- **A long-lived process keeps state your fix cannot reach.** It is alive, but
  what it is carrying may be months stale. Two forms bit the same daemon in one
  night. (a) A half-initialised module survives in `sys.modules`: a lazy `import`
  that dies partway (transient RPC/gRPC unavailability) leaves the module OBJECT
  behind, so every later import gets the empty shell and raises
  `AttributeError: module ... has no attribute X` forever, because Python never retries it. The
  tell is the FIRST failure differing from all the rest; a fresh process
  succeeds, which makes it read as "already self-healed". (b) The process's own
  `argv` freezes a path: a supervisor launched with a symlinked binary path keeps
  that string for its whole life, working fine until the restart that makes it
  re-exec, then `rc=127`, hours after the change that broke it. So a fix to
  resolution logic reaches only NEW processes. After changing how anything is
  located or imported, enumerate the long-lived processes still carrying the old
  argv or the old module, and state which ones must be recycled. When a restart
  hangs, suspect the launcher's frozen path before the code.
- **`AttributeError` where you expected `ImportError` means the module exists but
  is incomplete**: a partial init, not a missing dependency and not a version
  mismatch. Chasing a version skew here wastes the hour. Check whether a fresh
  process succeeds, which separates "the code is wrong" from "this process is
  poisoned".
- **Only `cron` + `setsid` survives on a workstation.** A daemon started from an
  agent or SSH shell is reaped when that session ends, within a minute, every
  time. `nohup ... &` straight from a cron entry dies too, because cron reaps the
  process group when its shell exits. Drive long-lived local work from a cron
  keepalive that `setsid`s the worker, make the keepalive idempotent (one
  instance per unit), and delete the entry when the work is done: a keepalive
  outliving its purpose becomes a second writer (`storage.md`).
- **A watcher that emits no alarm may be dead, not calm.** A `cron`+`setsid`
  entry that runs a script by path needs the execute bit. Rewriting that script
  drops the bit if the editor recreates the file, and then cron/`setsid` fail
  without a trace, because they swallow the error. The watcher never ticks, and
  everything it should have paged goes unseen for as long as the quiet lasts.
  After deploying or editing any keepalive or watcher, prove it actually ran (its
  own log advanced, or a self-test notification travelled the full chain end to
  end) before trusting silence. Absence of pages is equally the signature of a
  monitor that died on the launch pad.
- **Point `TMPDIR` at real disk before any long local job.** The default can be a
  small shared tmpfs, and at 100% full it deletes other processes' scratch and
  breaks job packaging with a no-space error after enough normal output to look
  like it worked. The same directory being wiped also destroys the launcher logs
  that map job ids to purpose.
- **A diagnostic probe is also load.** Repeatedly duplicating a 1.3 GB file to
  test a hypothesis, on a machine already saturated, worsens the contention being
  investigated, and can time out the shell running it. `engineering.md` §Do Not
  Let A Diagnostic Kill The Thing It Watches applies to ad-hoc probes, not just
  in-process guards.

## Porting Between Related Checkouts

- **Never sync a file wholesale.** Re-apply the local change as a hunk on top of
  the other side's version. A whole-file copy silently reverts what the local
  side had added: it still imports and the tests still pass. This produced a
  config knob that nine configs set and no code read, surviving eleven commits.
- **Grep for the READER, not the setter.** A setting nothing consumes is worse
  than a missing one: it promises behavior that does not exist.
- **A setting can arrive from somewhere that is not a config file.** A grep over
  every yaml can correctly report that nothing sets a knob while a CHECKPOINT
  sets it on every restore; a merged `extra.json` re-specified a model's compute
  dtype that way. When a value surprises you, ask what else writes it.
- **Related checkouts diverge deliberately.** Preserve each side's execution
  model, sharding, dependency, and initialization choices; never port runtime,
  data, or checkpoint behavior as incidental cleanup.

## Sharing One Worktree

Several agents committing into one checkout lose each other's work in ways that
look like tool corruption.

- **`git commit -- <pathspec>` IGNORES THE INDEX.** It re-reads those paths from
  the working tree, so a peer's uncommitted hunk in a file you also touched
  lands in your commit however carefully you staged. Put the pathspec on
  `git add`, check `git diff --cached` CONTENTS, then `git commit` with NO
  pathspec. Verify AFTER with `git show HEAD:<file>`, because `git diff --cached`
  is empty once the commit exists and reads as a false all-clear.
- **Never leave anything staged.** A `git rm` sitting in the index gets swept
  into someone else's commit and splits an atomic change in half.
- **Land a declaration with its implementation.** A config key declared in one
  commit and implemented in the next opens a window where a yaml sets a field
  the model does not have, and pydantic drops it in silence.
- **A suite run in a shared worktree is a smoke signal only.** Attribute nothing
  without a clean `git archive HEAD` export pinned to your own commit.

## External Writes Are Transactions

Establish identity and target, validate assumptions, write the smallest scope,
then read the result back. This covers buckets, spreadsheets, shared registries,
and any state another process can observe.

**Preserve the user's work**: never revert, overwrite, or clean a dirty worktree
as collateral. Before deleting shared or local data, identify the filesystem,
the owner, active references, and the recovery path; use a manifest for bulk or
shared deletion.

**Never kill by pattern.** `pkill -f` / `killall` signal every process whose
command line contains the string, including the shell running the command, which
on a workstation is a pane of the operator's tmux. A `pkill -f
'AGENT_WEB_PORT=8891'` aimed at one test server matched its own invocation and
took down the operator's entire tmux server: every daemon, session, and
terminal. The self-match also truncates the command that issued it, so a restart
written as one `pkill && start` line dies after the kill and never starts
anything. The thing you were restarting is left DOWN, the shell reports
`rc=-15`, and nothing says which half ran (measured 2026-08-30 on the budget
enforcer, which sat dead until the gap was noticed by hand). Resolve to PIDs
first (`ss -ltnp` for a port, `pgrep -a` / `/proc/<pid>/cmdline` to confirm what
each is), then signal those PIDs. `fuser -k` on a port is the same trap: check
who holds it first, and never assume a port is unused (8891 was a real service
someone else had added).

**The same pattern used to judge a process ALIVE fails in the opposite
direction: it revives a shadow.** A watchdog whose liveness test spells out the
flags (`--max-cancels 8 --jobs-file ...`) stops recognising the daemon the
moment anyone inserts an option between them, declares the healthy process dead,
and starts a second one from its own stored command line, which is the OLD one,
without whatever guard the new flag added. Measured 2026-08-30: adding
`--sustained-over-seconds=300` to the budget enforcer produced, 35 minutes later,
a second armed enforcer with no debounce and no `flock`. So match on the part
that cannot change (the binary, its registry file), never on the tunable flags;
have the watchdog revive through the SAME lock and flags the real launcher uses;
and treat a config change as an interface change. Before adding a flag, list
every reader of that process's observable surface, including the ones that read
its argv rather than its output.

**A process wedged in uninterruptible-D on a FUSE call is immune to SIGKILL and
to its siblings dying; only an srcfs restart's EIO-bounce frees it.** A holder
stuck in `request_wait_answer` (an unanswered CitC/FUSE request, e.g. an
xmanager orphan of a dead launcher) keeps whatever lock or fd it owns, and
tearing down the rest of its process tree does not release it: the kernel will
not deliver a fatal signal until the syscall returns. Restarting srcfs bounces
the hung syscall with EIO, the process finally dies, and the fd/lock closes.
That restart is fleet control-plane. It severs every CitC CWD, including the
amply gateway (`§Do Not Let A Diagnostic Kill` for the fallout), so it is
operator/sentinel-owned, never a casual fix. Two corollaries: attributing a
lock's release to "the sibling process died" is almost always a coincidence with
a concurrent srcfs restart, so check the restart log before believing it; and a
global D-count gate ("restart when procs_blocked ≥ N") MISSES a low-D-count
convoy where one orphan holds a lock with waiters queued behind it. Detect that
by the held lock plus its waiters, not by the aggregate count.

## A Tool Call Only Fires As A Structured Call, Never As Prose

**An action you "wrote out" but did not issue as a real, structured tool call
simply did not happen.** The message was never sent, the command never ran, the
job never launched, and it fails silently: no error, no output, just a
downstream party waiting on a thing that never came. The trap is writing the
call OUT (as tag-style markup, a fenced `bash` snippet, or a "calling
send_message…" sentence) into your REPLY TEXT instead of emitting it through the
tool channel. Reasons this recurs: composing a long narrative reply and pasting
the call inline; a call "interrupted" mid-turn by an incoming notification so
you re-narrate it rather than re-issue it; copying an example of a call verbatim
into prose.

- **If a turn's job is to DO something (send a message, run a command, edit a
  file), the turn's payload must be actual tool calls, not a description of
  them.** Prose is for talking to the human; it moves no state.
- **Confirm side-effecting calls landed before you claim them.** After a
  send/launch/write, read it back through the tool channel (the sent message is
  in the thread; the row is in the table; nmsg advanced). Do not report "sent"
  or "approved" from intent alone.
- **A call you wrote as text stays in your own history and reads as an example
  to copy.** One session that slipped once did it in 96 of its next 187 turns,
  stalling each time (median 24.7 min idle). If you catch it, re-issue the call
  as a real one immediately, and do not quote the bad output back; that only
  adds another example.
- **Highest stakes for safety-critical and cross-agent actions.** A dropped
  `send_message` leaves a peer blocked or a decision unmade; a dropped resume /
  `kill -CONT` can leave someone's process frozen. Treat an un-confirmed
  side-effecting call as NOT DONE.

## Communicating A Result

- **Define overloaded terms before using them.** *Step*, *update*, *iteration*,
  *cycle*, *task*, *segment* mean different things in different sources. Say
  concretely what the thing is and what it changes. When two sources collide on
  one word, flag the collision and introduce unambiguous local names BEFORE
  presenting any number.
- **A number is meaningless without its protocol**: what it counts, its unit,
  its denominator, what was held fixed, and whether higher is better. Two
  numbers are comparable only when those agree.
- **Separate what the evidence supports from what you inferred**, and keep a
  pointer to the original trace or log. A summary is a navigation aid, not a
  substitute for evidence.
- Lead with the outcome, keep prose short and load-bearing, and say plainly what
  you did not verify.
