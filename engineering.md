# Engineering Discipline

Read this before changing code, diagnosing a failure, or reporting a result, in
any checkout. It owns METHOD — the habits that are expensive to relearn.
`projects/` owns each codebase's semantics; `jobs.md` and `storage.md` own
infrastructure.

## Verify The Premise Before Changing Anything

- **Reproduce first.** Inspect the relevant code, tests, and recent history, and
  compare current behavior against the acceptance criteria. "No change needed"
  is a valid outcome — but a failed reproduction is not proof, since an earlier
  partial fix produces the same silence.
- **Prove the smallest thing that can fail, locally, before paying for a remote
  round trip.**
- **A green build proves the code compiles, not that it works.** Under relaxed
  dependency checking a missing import is a runtime error on the remote machine.
  Run the artifact — importing the whole graph (a `--help` invocation) costs
  seconds and catches the entire "died before `main()`" class.
- **Before claiming completion**, re-read the original request, run the most
  relevant checks, read their COMPLETE output, and compare the result against
  the request rather than against your patch. State whatever remains unverified.

## Diagnose From Evidence, Not From The Most Available Story

- **Read the deepest relevant failure, not the last line.** A traceback string
  alone is not a code bug: check for an earlier OOM, an environment error, or a
  swallowed exception upstream.
- **Distinguish "it was killed" from "it exited".** Different footprints — exit
  codes, attempt identity, failure counters, any shutdown marker the program
  writes itself — and opposite fixes.
- **A log's last LINE is not proof of life; its last WRITE TIME is.** A remote
  job's log persists after the job is preempted or dies, so the final `[step
  N/T]` reports where it STOPPED, not where it IS; re-reading the same static
  file confirms the stale number and reads as "healthy, unchanged" when it means
  "dead" (a monitor reported a run "healthy ~11%" three times off a log whose
  mtime was two hours old — preempted at that step). Check the log's mtime
  (`fileutil ls -l`) against now, or read authoritative scheduler state (`tpu
  check` / borg BCL), never the log body alone. Not advanced AND mtime older than
  a few minutes = preempted.
- **A cause that does not move when the suspect moves is not the cause.**
  Correlate the symptom's period or magnitude with the thing you suspect before
  acting on it.
- **A serial pipeline does not bound memory; standing servers do.** Each
  workspace's blaze server holds a multi-GB JVM heap for its whole
  `max_idle_secs` (days), one per checkout, whether or not a build runs; under
  pressure `--shutdown_on_low_sys_mem` evicts it and the next build is a cold
  heavy respawn that deepens the dip. Enumerate resident heaps (`ps` by RSS)
  before blaming concurrent builds — idle servers hold the memory, not overlap.
- **Two broken things can be true at once.** A real, measurable problem standing
  next to the failure is not automatically its explanation.
- **Absence of evidence is evidence.** No log, no status message, and no
  surviving handle together mean the failure happened before logging existed.
  Do not re-run to collect logs that cannot exist.

## A Test That Cannot Fail Proves Nothing — And Often Finds The Bug

**Write the negative control before believing a checker**, and prefer a test
over another hour of reading logs.

A verifier only ever run against good data is untested; `storage.md` records a
mirror check that compared a constant against itself and passed against a
nonexistent destination. So for every checker, break exactly one property —
truncate the payload, duplicate a key, shorten an index array, flip one byte
while keeping the length — and require the verdict to flip.

**The fault you inject is itself a measurement.** Two hours of log-reading on
four identical failures yielded only a plausible story ("storage flaky under
concurrency"); the retry test took minutes and made the real cause obvious — the
injected fault left the destination *smaller* than the boundary, an append
cannot shrink a file, so another process was writing. A test that encodes what
must be true converts a guess into a contradiction.

Corollaries worth the line:

- **Report a violation as a verdict, not an exception**, where one bad item
  would otherwise abort the whole report and hide every other finding.
- **Keep the slow, obvious implementation** when you optimise a reader, and
  assert the fast one equals it. Batching reads reorders results, and scoring
  row A's label against row B's board looks entirely plausible.
- **A test written against a name that does not exist is the test working** —
  that drift between a config and the table it must agree with is exactly what
  it is there to catch.

## Do Not Let A Diagnostic Kill The Thing It Watches

Guards, validators, and telemetry run inside the job but are not the job. Put
them behind a total comparison that can answer "can't tell", make them swallow
their own failures, and never let one raise into a training or serving loop. A
check that can crash a run has negative value.

**A monitor that hardcodes an endpoint reports a false mass-death when that
endpoint moves.** The amply UX gateway (the `:PORT` server behind the web UI and
cross-run query tools) has no stable port: on crash (e.g. LOAS2 expiry) it
relaunches on a *fresh* port and rewrites `~/.amply/dashboard_url`. Workers are
reparented to init and survive (verify `pgrep -af 'amply worker|claude-amply.py
resume'` + `ps -o ppid`: PPID=1 = independent of the gateway). A watcher
hardcoding the old port probes a dead socket and pages every session DEAD in one
second — false alarm. Defenses: (1) read the base URL from
`~/.amply/dashboard_url`, never hardcode a port; (2) treat a *simultaneous*
all-sessions DEAD with `Connection refused` as gateway-down-until-proven, confirm
workers alive first, and NEVER `amp start`/kill a worker to "recover" (that is
what kills a live session). The gateway self-heals; repoint the observer, not the
observed.

**While diagnosing a stuck healer, read its state — do not invoke it.** A probe
that runs the self-heal script (even `--help`) can trigger its side effect: a
rebuild whose `blaze` child outlives your `timeout` wrapper, orphaning to init
and joining the exact concurrent-build storm you are investigating. The
`timeout` kills the wrapper, not the grandchild it already forked. Inspect the
binary, the lock, and the logs directly; run the healer only once, deliberately,
after you understand the state — never as a way to observe it.

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
- **Only `cron` + `setsid` survives on a workstation.** A daemon started from an
  agent or SSH shell is reaped when that session ends — within a minute, every
  time — and `nohup ... &` straight from a cron entry dies too, because cron
  reaps the process group when its shell exits. Drive long-lived local work from
  a cron keepalive that `setsid`s the worker, make the keepalive idempotent
  (one instance per unit), and **delete the entry when the work is done**: a
  keepalive outliving its purpose becomes a second writer (`storage.md`).
- **A watcher that emits no alarm may be dead, not calm.** A `cron`+`setsid`
  entry that runs a script *by path* needs the execute bit; rewriting that
  script — an editor that recreates the file silently drops the bit — makes
  cron/`setsid` fail without a trace, because they swallow the error. The
  watcher never ticks, and everything it should have paged goes unseen for as
  long as the quiet lasts. After deploying **or editing** any keepalive or
  watcher, prove it actually ran — its own log advanced, or a self-test
  notification travelled the full chain end to end — before trusting silence:
  absence of pages is not evidence of health, it is equally the signature of a
  monitor that died on the launch pad.
- **Point `TMPDIR` at real disk before any long local job.** The default can be
  a small shared tmpfs, and at 100% full it deletes other processes' scratch and
  breaks job packaging with a no-space error *after* enough normal output to look
  like it worked. The same directory being wiped also destroys the launcher logs
  that map job ids to purpose.
- **A diagnostic probe is also load.** Repeatedly duplicating a 1.3 GB file to
  test a hypothesis, on a machine already saturated, worsens the contention being
  investigated — and can time out the shell running it. `engineering.md`
  §Do Not Let A Diagnostic Kill The Thing It Watches applies to ad-hoc probes,
  not just in-process guards.

## Porting Between Related Checkouts

- **Never sync a file wholesale.** Re-apply the local change as a hunk on top of
  the other side's version. A whole-file copy silently reverts what the local
  side had added, invisibly — it still imports and the tests still pass. This
  produced a config knob that nine configs set and no code read, surviving
  eleven commits.
- **Grep for the READER, not the setter.** A setting nothing consumes is worse
  than a missing one: it promises behavior that does not exist.
- **A setting can arrive from somewhere that is not a config file.** A grep over
  every yaml can correctly report that nothing sets a knob while a CHECKPOINT
  sets it on every restore — a merged `extra.json` re-specified a model's
  compute dtype that way. When a value surprises you, ask what else writes it.
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
  pathspec — and verify AFTER with `git show HEAD:<file>`, because
  `git diff --cached` is empty once the commit exists and reads as a false
  all-clear.
- **Never leave anything staged.** A `git rm` sitting in the index gets swept
  into someone else's commit and splits an atomic change in half.
- **Land a declaration with its implementation.** A config key declared in one
  commit and implemented in the next opens a window where a yaml sets a field
  the model does not have — and pydantic drops it in silence.
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
command line contains the string — including the shell running the command,
which on a workstation is a pane of the operator's tmux. A `pkill -f
'AGENT_WEB_PORT=8891'` aimed at one test server matched its own invocation and
took down the operator's entire tmux server — every daemon, session, and
terminal. Resolve to PIDs first (`ss -ltnp` for a port, `pgrep -a` /
`/proc/<pid>/cmdline` to confirm what each is), then signal those PIDs. `fuser
-k` on a port is the same trap: check who holds it first, and never assume a port
is unused (8891 was a real service someone else had added).

**A process wedged in uninterruptible-D on a FUSE call is immune to SIGKILL and
to its siblings dying — only an srcfs restart's EIO-bounce frees it.** A holder
stuck in `request_wait_answer` (an unanswered CitC/FUSE request, e.g. an
xmanager orphan of a dead launcher) keeps whatever lock or fd it owns, and
tearing down the rest of its process tree does not release it: the kernel will
not deliver a fatal signal until the syscall returns. Restarting srcfs bounces
the hung syscall with EIO, the process finally dies, and the fd/lock closes.
That restart is fleet control-plane — it severs every CitC CWD, including the
amply gateway (`§Do Not Let A Diagnostic Kill` for the fallout) — so it is
operator/sentinel-owned, never a casual fix. Two corollaries: attributing a
lock's release to "the sibling process died" is almost always a coincidence with
a concurrent srcfs restart, so check the restart log before believing it; and a
global D-count gate ("restart when procs_blocked ≥ N") MISSES a low-D-count
convoy where one orphan holds a lock with waiters queued behind it — detect that
by the held lock plus its waiters, not by the aggregate count.

## A Tool Call Only Fires As A Structured Call, Never As Prose

**An action you "wrote out" but did not issue as a real, structured tool call
simply did not happen** — the message was never sent, the command never ran, the
job never launched — and it fails SILENTLY: no error, no output, just a
downstream party waiting on a thing that never came. The trap is writing the
call OUT — as tag-style markup, a fenced `bash` snippet, or a "calling
send_message…" sentence — into your REPLY TEXT instead of emitting it
through the tool channel. Reasons this recurs: composing a long narrative reply
and pasting the call inline; a call "interrupted" mid-turn by an incoming
notification so you re-narrate it rather than re-issue it; copying an example of
a call verbatim into prose.

- **If a turn's job is to DO something (send a message, run a command, edit a
  file), the turn's payload must be actual tool calls — not a description of
  them.** Prose is for talking to the human; it moves no state.
- **Confirm side-effecting calls landed before you claim them.** After a
  send/launch/write, read it back through the tool channel (the sent message is
  in the thread; the row is in the table; nmsg advanced). Do not report "sent"
  or "approved" from intent alone.
- **A call you wrote as text is poison in your own history.** It stays in the
  transcript and reads as an example to copy: one session that slipped once did
  it in 96 of its next 187 turns, stalling each time (median 24.7 min idle). If
  you catch it, re-issue the call as a real one immediately, and do not quote the
  bad output back — that only adds another example.
- **Highest stakes for safety-critical and cross-agent actions.** A dropped
  `send_message` leaves a peer blocked or a decision unmade; a dropped resume /
  `kill -CONT` can leave someone's process frozen. Treat an un-confirmed
  side-effecting call as NOT DONE.

## Communicating A Result

- **Define overloaded terms before using them.** *Step*, *update*, *iteration*,
  *cycle*, *task*, *segment* mean different things in different sources. Say
  concretely what the thing is and what it changes; when two sources collide on
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
