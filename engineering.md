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
- **A cause that does not move when the suspect moves is not the cause.**
  Correlate the symptom's period or magnitude with the thing you suspect before
  acting on it.
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

**The fault you inject is itself a measurement.** Chasing four identical
failures at one offset, two hours of log-reading produced only a plausible story
("the storage layer is flaky under concurrency"). Writing the retry test took
minutes: the injected fault left the destination *smaller* than the boundary,
the code refused it with the arithmetic spelled out, and that made the real
cause obvious — an append cannot shrink a file, so another process was writing.
A test that encodes what must be true converts a guess into a contradiction.

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
