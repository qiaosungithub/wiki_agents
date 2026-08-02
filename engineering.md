# Engineering Discipline

Read this before changing code, diagnosing a failure, or reporting a result, in
any checkout. It holds the habits that are expensive to relearn. Project guides
under `projects/` own semantics; this file owns method.

## Verify The Premise Before Changing Anything

- Reproduce when feasible; inspect the relevant code, tests, and recent history;
  compare current behavior against the acceptance criteria. "No change needed"
  is a valid outcome, but a failed reproduction is not proof — account for a
  partial or incorrect earlier fix.
- Before claiming completion, re-read the original request, run the most
  relevant checks, read their **complete** output, and compare the result with
  the request rather than with your patch. State whatever remains unverified.
- A green build proves the code compiles, not that it works. Under relaxed
  dependency checking a missing import is a runtime error on the remote machine,
  so run the artifact — importing the whole graph (for example a `--help`
  invocation) costs seconds and catches the entire "died before `main()`" class.
- Prove the smallest thing that can fail, locally, before paying for a remote
  round trip.

## Diagnose From Evidence, Not From The Most Available Story

- Read the deepest relevant failure, not the last line. A traceback string alone
  is not a code bug; check for an earlier OOM, an environment error, or a
  swallowed exception upstream.
- **Distinguish "it was killed" from "it exited".** They have different
  footprints — exit codes, attempt identity, failure counters, and any shutdown
  marker the program writes itself. A process that leaves voluntarily and one
  that is destroyed need opposite fixes.
- **A cause that does not move when the suspect moves is not the cause.**
  Correlate the symptom's period or magnitude with the thing you suspect before
  acting on it.
- Two slow or broken things can be true at once. A real, measurable problem
  standing next to the failure is not automatically its explanation.
- Absence of evidence is itself evidence: no log, no status message, and no
  surviving handle together mean the failure happened before logging existed.
  Do not re-run to collect logs that cannot exist.

## Do Not Let A Diagnostic Kill The Thing It Watches

Guards, validators, and telemetry run inside the job but are not the job. Put
them behind a total comparison that can answer "can't tell", swallow their own
failures, and never raise into a training or serving loop. A check that can
crash a run has negative value.

## Failure Modes That Only Appear On The Long Path

- **A short run does not validate resume.** The cold-start path and the restore
  path touch different data: a fresh tree holds arrays, a restored one also
  holds optimizer state whose leaves include `None`, scalars, and containers.
  Budget one deliberate restart before trusting a multi-hour schedule.
- **Code that runs every N steps fails N steps in.** Mocked or stubbed libraries
  raise at call time, not import time. Probe with `getattr` and degrade.
- **Anything that installs a handler can steal a stream someone else installed.**
  Verify the side effect after constructing logging, tracing, or writer objects,
  rather than assuming composition.

## Porting Between Related Checkouts

**Never sync a file wholesale.** Re-apply the local change as a hunk on top of
the other side's version. A whole-file copy silently reverts whatever the local
side had added, and the loss is invisible because the file still imports and the
tests still pass. This exact mistake produced a config knob that nine configs set
and no code read, surviving eleven commits.

When a knob or flag looks suspicious, **grep for the reader, not the setter**. A
setting nothing consumes is worse than a missing one: it promises behavior that
does not exist.

Related checkouts diverge deliberately. Preserve each side's execution model,
sharding, dependency, and initialization choices; do not port runtime, data, or
checkpoint behavior as incidental cleanup.

## External Writes Are Transactions

Establish identity and target, validate assumptions, write the smallest scope,
then read the result back. This applies to buckets, spreadsheets, shared
registries, and any state another process can observe.

Preserve the user's work: never revert, overwrite, or clean a dirty worktree as
collateral. Before deleting shared or local data, identify the filesystem, the
owner, active references, and the recovery path; use a manifest for bulk or
shared deletion.

## Communicating A Result

- **Define overloaded terms before using them.** Words like *step*, *update*,
  *iteration*, *cycle*, *task*, and *segment* mean different things in different
  sources. On first use, say concretely what the thing is and what it changes;
  when two sources collide on one word, flag the collision and introduce
  unambiguous local names before presenting any number.
- A number is meaningless without its protocol: what it counts, its unit, its
  denominator, what was held fixed, and whether higher is better. Two numbers are
  comparable only when those agree.
- Separate what the evidence supports from what you inferred, and keep a pointer
  to the original trace or log. A summary is a navigation aid, not a substitute
  for evidence.
- Lead with the outcome, keep prose short and load-bearing, and say plainly what
  you did not verify.
