# Evidence And Verification

## Evidence Order

**When facts disagree, prefer this order:**

1. The user's current request.
2. Current repository code and repository-native docs.
3. Live infra state, logs, WandB, and the spreadsheet.
4. The core guides in this folder.
5. [archive/](../archive), which is historical evidence only.

**To claim that X works, is allowed, or fits, perform X once; do not query a
status that describes X.** A status query usually measures the neighboring thing,
and it fails in the expensive direction, because it looks like supporting
evidence. The hard part is stating what the claim actually asks.

| The claim | The status query that looks right | What it actually measures |
|---|---|---|
| This slice will fit the model | Total HBM across the slice | Per-chip HBM binds when weights are replicated; the total binds only under model parallelism |
| This card is free | `tou` shows it `IDLE` | A visibility view, not the infra owner, the tmux window, or a remote process holding the devices ([harness/skills/infra-operations/SKILL.md](skills/infra-operations/SKILL.md)) |
| That agent or job is still alive | A process holds its log, or a dashboard says it is running | That some process writes a file; dashboards go stale and are not authoritative |
| My mail was sent | The EWS request returned HTTP success | That the service accepted a request, not that the item exists; read it back ([harness/skills/mit-email/SKILL.md](skills/mit-email/SKILL.md)) |
| This will never finish, or never be released | It makes no progress now, and every way it could finish is ruled out | That it is stuck at this instant; a slow counterpart can still return, and the exits you did not think of are not ruled out |
| This job hung | Its log stopped growing | One attempt's log; a resumed chain runs a new attempt, and the frozen file can belong to an old one |
| My watcher would have told me | The watcher process is alive and silent | That a process runs; not that it watches the right id, nor that its probe can express the failure you fear |
| These repeated numbers disagree, so something is being sampled | The spread across runs | Dispersion you never compared with the noise floor: at n=1319 and p≈4.5%, the binomial sd is 0.571 pt, so a 0.531 pt spread is expected |
| This stale state will be cleaned up automatically | The cleanup function, called by hand, returns the right verdict | That the logic is correct, not that anything calls it |

The "never finish" row is the one that reads as a verdict. The observation
describes now, while the question is about later, so say "I do not know when it
will be released", never "it will not be released".

**Before a negative reading becomes a conclusion, name the five coordinates the
instrument points at: which process, which attempt, which time window, which
output path, and whether the code you verified is ever invoked.** Each can be
wrong while the reading is true: an idle worker that never owned the queue, a
frozen log from a dead attempt, a spread judged without its noise floor, a line
printed before its log mirror existed. When a file, variable, or chart carries a
name you gave it earlier, re-derive which artifact it holds before reasoning from
it. A baseline file once stitched a resumed run onto a run that never resumed,
and the merged history showed a spike pattern neither run had.

**Testing a function proves it can do the job, not that anything calls it.** A
cleanup routine can return exactly the right verdict when run by hand while no
process ever invokes it, so the table it should clean stays stale for days. Check
the caller, the service, or the cron entry, not only the callee.

**Treat an absence as a question about the instrument first and the world
second.** A missing log line, an unclaimed job, a silent watcher, and a stalled
file each have two readings: the thing did not happen, or you cannot see it from
here. The second is usually cheaper to check, so every probe needs a case in
which it is known to speak.

**A silent success is more dangerous than a clean failure**, because a failure
leaves a trace and `rc=0` makes every check look green. Close the loop at the far
end: confirm the message arrived in the recipient's stream, and confirm the job
reached running and wrote its own verdict.

**Check that the value you read came from the command you ran.** A shell pipeline
reports the exit status of its last stage, so `cmd | head` reads `head`'s success
and hides `cmd`'s failure. Capture with `out=$(cmd 2>&1); rc=$?`, or redirect to
a file. `${PIPESTATUS[0]}` is itself a trap: any intervening statement, including
the `rc=$?` assignment meant to save it, resets the array.

**A pipe truncates the answer as well as the status.** `| head -N` drops content
invisibly, and the output still looks complete. An item that vanishes from a
windowed listing may only have been pushed out by a new one, so count first or
read the whole output.

**A failed reproduction refutes only when it reproduces the conditions.** The
same probe against a different workspace, or a 3-second window against a
30-minute effect, cannot see what it claims to rule out. State what the negative
result covers.

**When someone corrects you, verify the method their correction rests on, not
only its conclusion.** Once a claim has passed through two people who each
checked only the other's downstream reasoning, the faulty premise is the part
nobody re-examines.

**Hedging a number does not make it right; a second, independent route to the
same answer does.** Before quoting a number that someone will plan against,
derive it another way: a different instrument, window, or artifact. With only one
route, hedge the range rather than your posture: "about two hours, from a single
six-minute window, so possibly several times that" invites a check, where "about
2.1 hours (rough)" does not. A rate measured during startup, catch-up, or backlog
drain is not the steady state.

**When you act on something you were told rather than saw, go back to the source
first.** Hedges do not survive relay, so a claim grows more confident the further
it travels from the person who knows how weak it is. Do this whenever the next
step is hard to walk back: editing shared docs, changing a config, killing
something. Agreement is not corroboration when it is the same evidence arriving
twice, so count distinct methods, not distinct agreers.
