# Engineering Discipline

Method for changing code, diagnosing failures, and reporting results in any
checkout. **Chapter 1** is the principles — one sentence each, so you can scan them
all in a minute. The concrete drill for writing and running NEW code against our
fleet is the [local-debug](skills/local-debug/SKILL.md)
skill. The rules for every task are in [policy.md](policy.md#global-rules), the
evidence rules in [evidence.md](evidence.md#evidence-order).
[`projects/`](../knowledge/codebases/projects.md) owns each codebase's semantics;
[knowledge/infrastructure/cluster-jobs.md](../knowledge/infrastructure/cluster-jobs.md) and [knowledge/infrastructure/storage.md](../knowledge/infrastructure/storage.md) own infrastructure; workstation upkeep
lives in [knowledge/environment/workstation.md](../knowledge/environment/workstation.md) and [`infra/`](../knowledge/infrastructure/market.md).

## Chapter 1 — Principles

Each line is a rule, not a story. The evidence that earned it is in git history;
what matters here is that none of it is buried.

### Before you change anything
- Reproduce the problem first; "no change needed" is a valid outcome.
- A failed reproduction is not proof, because an earlier partial fix produces the same silence.
- Prove the smallest thing that can fail locally before paying for a remote round trip ([local-debug](skills/local-debug/SKILL.md#local-debug-then-remote-before-a-real-run)).
- Before claiming done, re-read the original request and check the complete output against it, not against your patch.

### Trust artifacts, not success returns
- A green build proves the code compiles, not that it runs — import or `--help` the artifact.
- A CLI can reject your flag and still exit 0, so read the OUTPUT of a state-changing command, not just its `rc`.
- After any edit, read the file back and assert the change is actually on disk.
- Read it back with an instrument that answers your real question (`grep -c` proves text exists, not that a method is attached to its class).
- A cached green build describes the tree as it was when cached, so pass `--nocache_test_results` when the verdict is load-bearing.
- A shell pipeline reports its LAST stage's status, so `cmd | head` hides `cmd`'s failure — capture `rc` on the very next line.

### Make edits atomic
- A change spanning a definition and its callers belongs in ONE edit, or a sibling's build samples the broken window.
- Deleting a file means deleting every reference to it, so grep the name first and build with `--keep_going`.

### Diagnose from evidence, not the most available story
- Read the deepest relevant failure, not the last line, because an OOM or a swallowed exception upstream is the real cause.
- Distinguish "it was killed" from "it exited" — different footprints, opposite fixes.
- A log's last LINE is not proof of life; its last WRITE TIME is.
- A cause that does not move when the suspect moves is not the cause.
- Two broken things can be true at once, so a real problem next to the failure is not automatically its cause.
- Absence of evidence is evidence: no log and no handle means the failure happened before logging existed.

### A test that cannot fail proves nothing
- Write the negative control first — break one property and require the verdict to flip.
- Assert on the artifact the next reader actually consumes (an exit code, a file, a counter), not the nearest thing that moved.
- Test a fix at a LARGER input than today's, never a smaller one, because shrinking the input hides the slope.
- Put the freshness check inside the reader, or a statistic over a frozen file reads as converged.
- Force a selector to select nothing and then to select everything before trusting what it picked.
- Report a violation as a verdict, not an exception, so one bad item does not hide every other finding.
- Keep the slow obvious implementation and assert the fast one equals it.
- Inject faults into a `/tmp` copy, never a shared file, and put the restore in a `trap` so a kill still cleans up.

### When a reading is wrong, fix the predicate, not the command
- A correction re-runs the measurement; it does not fix a broken way of READING it.
- Re-check the subject too: in a dirty worktree `HEAD` and the file on disk are different objects, so name which one you measured.
- When a second measurement contradicts the first, chase it — especially when the first one flatters you.
- Hedging a number does not make it right; a second independent route to the same value does.
- Correct a retracted number everywhere it landed, including the source comment that quotes it.

### Guards and diagnostics must not kill the job
- A guard, validator, or telemetry hook must swallow its own failure and never raise into a training or serving loop.
- A guard threshold is a claim about floats, not algebra, so evaluate the expression at extreme inputs (underflow makes `exp(-tiny)` round to exactly 1.0).
- Check whether a statistic is a max, a mean, or a sample before treating it as a property of the whole object.
- While diagnosing a stuck healer, read its state; do not invoke it, even with `--help`.
- A memory cap without a swap cap is not a cap, so set `MemoryMax` AND `MemorySwapMax=0`.
- A diagnostic probe is also load, so do not investigate a saturated machine by adding to its saturation.

### Long-lived processes and the long path
- A short run does not validate resume, so budget one deliberate restart before trusting a multi-hour schedule.
- Code that runs every N steps fails N steps in, because stubbed libraries raise at CALL time, not import.
- A long-lived process keeps state your fix cannot reach — a half-initialised module in `sys.modules`, or a path frozen in its argv.
- `AttributeError` where you expected `ImportError` means the module exists but is incomplete, not a version skew, and a fresh process tells you which.
- After changing how anything is located or imported, name which long-lived processes still carry the old argv and must be recycled.
- Only `cron` + `setsid` survives on a workstation; a daemon from an agent or SSH shell is reaped when the session ends.
- A watcher that emits no alarm may be dead, not calm, so prove it ran before trusting its silence.

### External writes are transactions
- Treat any external write as a transaction: establish identity and target, validate, write the smallest scope, then read it back.
- Preserve the user's work — never revert or clean a dirty worktree as collateral, and use a manifest for bulk or shared deletion.
- Never kill by pattern; `pkill -f` matches the shell that runs it, so resolve to PIDs first.

### Sharing one worktree
- In an autonomous run, tell your OWN worker from a PEER by matching the argv task before you react to it.
- `git commit -- <pathspec>` IGNORES THE INDEX and re-reads the worktree, so it sweeps in a peer's uncommitted hunk — put the pathspec on `git add` instead.
- Never leave anything staged; a stray `git rm` gets swept into someone else's commit.
- Land a declaration with its implementation, or a config sets a field the code does not yet have.

### Porting between related checkouts
- Never sync a file wholesale; re-apply the local change as a hunk, or the copy silently reverts what the local side added.
- Grep for the READER, not the setter, because a setting nothing consumes is worse than a missing one.
- A value can arrive from a checkpoint or a merged `extra.json`, not only a config file.

### A tool call only fires as a structured call
- An action you "wrote out" as prose but did not issue as a real tool call simply did not happen, and it fails silently.
- If a turn's job is to DO something, its payload must be actual tool calls, because prose moves no state.
- Confirm a side-effecting call landed (the message is in the thread, the row is in the table) before you claim it.

### Communicating a result
- Define overloaded terms (step, update, iteration, cycle) before using them.
- A number is meaningless without its protocol: what it counts, its unit, its denominator, what was held fixed, and whether higher is better.
- Separate what the evidence supports from what you inferred, and keep a pointer to the trace.
- Lead with the outcome, keep the prose load-bearing, and say plainly what you did not verify.
