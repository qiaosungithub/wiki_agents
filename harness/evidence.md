# Evidence And Verification

This page owns the evidence rules for every task: which source wins when facts
disagree, and how to check that a reading measures the claim. Its sibling pages
are [policy.md](policy.md#global-rules) (the rules for every task) and
[engineering.md](engineering.md) (the working method).

## Evidence Order

The user's request, then current code and native docs, then live infra state and
logs, then these guides, then [`archive/`](../archive/README.md) (history only).

**To assert that X has permission / fits / will be received, perform X once. Do
not query a status that describes X.** A status query almost always measures the
adjacent thing, and it fails in the most expensive direction: it looks like
supporting evidence. The hard part is not finding evidence, it is stating what
the claim actually asks.

| The claim | The status query that looks right | What it actually measures |
|---|---|---|
| This slice will fit the model | total HBM across the slice | per-chip HBM, when weights are replicated (`model_size=1`); totals bind only under model parallelism |
| I lack membership in a group | `aclcheck` returns `PERMISSION_DENIED` | whether you may read the ACL; a sandbox that cannot reach the ACL proxy denies identically |
| This capacity is usable | the router shows the shape `PLACEABLE` | that an availability RPC answered; not the budget gate, the authorization, or preemption |
| That agent still exists | a writer holds its log, or a dashboard says `ongoing` | that some process writes a file; dashboards go stale and are not authoritative |
| My alert reached the on-call | the notify call returned `rc=0` | that *a* worker accepted it, possibly a retired session nobody reads |
| This will never finish / never be released | it is making no progress now, and the ways it could finish are all ruled out | that it is stuck at this instant; a very slow counterpart can still return, and ruling out the exits you thought of is not ruling out the ones you did not |
| Nobody will pick up this queued job | the serial build worker is idle and has not claimed it | a different process's state; `BUILD_REQUESTED` is claimed by the dispatch worker, so the serial worker's idleness says nothing about it |
| This flag did not take effect | the job's log never printed the override line | output emitted before the log sink was started; a value announced ahead of `_start_telemetry` exists only in a Borg stderr that is GC'd in minutes |
| This job hung | its log stopped growing | one attempt's log; a retried job writes `..._attempt2.log`, and the frozen file belongs to the attempt that died |
| My watcher would have told me | the watcher process is alive and silent | that a process is running; not that it watches the right id, nor that its probe can express the failure you fear |
| These repeated numbers disagree, so something is being sampled | the spread across runs | dispersion you never compared to the noise floor; at n=1319, p≈4.5%, binomial sd is 0.571 pt and a 0.531 pt spread is expected |
| This stale row will be cleaned up automatically | the reconcile FUNCTION, called by hand, returns the right verdict | that the logic is correct, not that anything calls it: the daemon logged `reroute pass SKIPPED (standalone owner)` for a standalone process nobody had started, and 63 of 84 queue rows were zombies, the oldest 179 h stale |

The "will never finish" row is the one that reads as a verdict. The reading is
correct, but it describes now and the question is about later. Say "I do not
know when it will be released", never "it will not be released"; when a fix or a
fresh sample proves it wrong, the observation was never wrong, only its tense.
In every other row the query measured the neighbouring thing.

**Before a negative reading becomes a conclusion, name the five coordinates the
instrument is pointed at: which PROCESS, which ATTEMPT, which TIME WINDOW, which
OUTPUT PATH, and whether the code you verified is ever INVOKED.** One line of
work missed a different one of these on five consecutive occasions in a single
shift, every time with a reading that was perfectly true. Wrong process: the
serial worker was idle, but the dispatch worker owned that queue state. Wrong
attempt: the log froze because it belonged to a dead retry while `attempt2` ran
fine. Wrong window: a spread was called a sampling bug without computing the
binomial sd it had to beat. Wrong path: the override line was printed before the
CNS mirror existed. The fifth is the one no checklist catches: the data was real
but described two different objects. A baseline file stitched a resumed run onto
a run that never resumed, and the merged history "proved" a spike pattern
neither arm had. Whenever a file, a variable, or a chart carries a name you gave
it earlier, re-derive which artefact it holds before you reason from it. The
name is your old belief, not evidence.

**The INVOKED coordinate is the one that survives careful review, because
testing a pure function proves capability and says nothing about occurrence.** A
reconcile routine was exercised directly, returned exactly the right verdict,
and was cited as proof that stale rows self-clean, while no process on the
machine ever called it, so a status table sat 179 hours out of date and read as
live. "It would handle this correctly" and "it is handling this" are different
claims, and only the second is evidence. Check the caller, the service, the cron
entry, not just the callee.

**An absence is the weakest possible reading, so treat "X did not appear" as a
question about the instrument first and the world second.** A missing log line,
an unclaimed job, a silent watcher and a stalled file all have two readings: the
thing did not happen, or you cannot see it from here. The second is usually
cheaper to check. A watcher that has never fired is indistinguishable from a
watcher pointed at the wrong id, so every probe needs a case in which it is
known to speak.

The `rc=0` row is the general case: **a silent success is more dangerous than a
clean failure**, because failure leaves a trace and `rc=0` makes every check look
green. Close the loop at the far end. Confirm the message arrived in the
recipient's stream, and confirm the job reached `RUNNING` and wrote its own
verdict.

**Then check that the value you read came from the command you ran.** A shell
pipeline reports the exit status of its last stage, so `cmd | head` reads
`head`'s success and hides `cmd`'s failure. Capture with
`out=$(cmd 2>&1); rc=$?`, or redirect to a file. `${PIPESTATUS[0]}` is itself a
trap: any intervening statement, including the `rc=$?` assignment meant to save
it, resets the array. Having performed X is not enough if the reading instrument measures
something else, and that mistake survives review because the number is real and
reproducible.

**A pipe truncates the answer as well as the status.** `| head -N` drops content
invisibly: the output still looks complete, because it was always meant to be
several lines. An item that vanishes from a windowed listing has not necessarily
vanished; it may have been pushed out by a new one. A disappearance is only
evidence once you know the total, so count first or read it whole.

**A failed reproduction only refutes when it reproduces the conditions.**
Running the check somewhere else, or on a shorter timescale than the effect,
turns a refutation into an unrelated success: the same probe against a different
workspace, or a 3-second window against a 30-minute one, cannot see the thing it
claims to rule out. State what the negative result covers, not what it feels
like.

**When someone corrects you, verify the method their correction rests on, not
just its conclusion.** Once a claim has passed through two people who each only
checked the other's downstream reasoning, the faulty premise is what nobody
re-examines. A self-correcting process beats an infallible one, but only while
each round re-checks premises rather than conclusions.

**Hedging a number does not make it right; a second, independent route to the
same answer does.** "Rough estimate, timestamped, not claiming precision" is a
statement about your confidence, not about the value, and it can sit in front of
a figure that is wrong by a factor of five while making it read as measured. The
same holds for a well-formed method list in front of a false conclusion. Before
quoting a number that someone will plan against, derive it a second way: a
different instrument, a different window, a different artifact. If you only have
the one, hedge the range rather than your posture. "About two hours, from a
single six-minute window, so possibly several times that" invites the reader to
check, where "about 2.1 hours (rough)" does not. Beware a slope measured across
a transient: a rate taken during startup, catch-up or backlog drain is not the
steady state, and a window is long enough only when it does not consist of a
single phase.

**When you act on something you were told rather than something you saw, go back
to the source first.** Hedges do not survive relay: whoever passes a finding
along copies the conclusion and drops the "(unverified)", so a claim gets more
confident the further it travels from the person who knows how weak it is. One
round trip to the original, asking whether they marked this unproven, costs
seconds. It is worth it whenever the next step is hard to walk back: editing
shared docs, changing a config, killing something. Agreement is not corroboration
when it is the same evidence arriving twice, nor when several people ran the same
incomplete checklist. Count distinct methods, not distinct agreers.
