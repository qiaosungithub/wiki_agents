# Workspace Memory

This folder holds the small amount of shared context an agent needs before
working under `/kmh-nfs-ssd-us-mount/code/qiao/work`. The user's request, current
code, and live state outrank it (§Evidence Order).

## Start Here

1. Read this file, then `engineering.md`, the working method for any task.
2. Read `projects.md` to identify the checkout and its native documentation.
3. Read only the topic guides the router names for the task. Do not read every
   guide.
4. Inspect the current code, git state, and live system before acting. These
   guides explain intent and invariants; they are not a substitute for current
   source or runtime state.

## Workspace Model

**This is a shared research workspace with many independent repositories and a
shared NFS mount, so a task's scope is the checkout the user named, not the whole
workspace.**

- `unified_infra` and its `infra` CLI are the current TPU job system. Legacy xibo tools remain only for a few inspection, mount, copy, and cleanup tasks.
- Training data and checkpoints are region-local. Metadata is cheap to inspect; large payloads are not safe to move or read across regions by default.
- Agent memory should capture durable decisions and non-obvious invariants. Exact commands, incident timelines, job ids, and old configurations belong in source docs, live state, experiment records, or `archive/`.

## Layout

**The wiki stays flat because other checkouts and the user's notes link to these
file names, so fix those links before moving or renaming a page.**

| Path | Owns |
|---|---|
| `AGENTS.md` | Rules for every task, the evidence rules, and the router |
| `engineering.md` | Method: the principles (Chapter 1) and the local-then-remote debug drill (Chapter 2) |
| `memory.md` | How this wiki is organized, and how to write or rewrite a page |
| `projects.md` | The checkout map and the boundaries between checkouts |
| `infra.md` | Queueing, inspecting, resuming, and cleaning up TPU jobs |
| `storage.md` | Reclaiming disk space safely, and deciding whether an artifact or copy is complete |
| `vlm_training.md`, `vlm_data.md`, `vlm_metrics.md` | The VLM checkouts: training code, data and benchmarks, reporting a score |
| `research.md`, `spreadsheet.md` | Running an experiment loop; logging its results |
| `paper_reading.md`, `paper_rendering.md` | Writing a paper report; rendering its HTML and PDF |
| `email.md` | The MIT mail account |
| `research/` | Research idea pages |
| `archive/` | History, never routed to by default (`archive/README.md`) |

## Topic Router

| Task | Read |
|---|---|
| Anything, before you start | `engineering.md` |
| Add to or reorganize this wiki; where a note belongs; shape or rewrite a page | `memory.md`, then §Maintaining Memory |
| After a large code change, before queueing a real run | `engineering.md` Chapter 2 |
| Write a checker, or a verification keeps saying OK | `engineering.md` §A test that cannot fail proves nothing |
| An edit reported success but the change is missing | `engineering.md` §Trust artifacts, not success returns |
| Two measurements disagree, or a number was retracted | `engineering.md` §When a reading is wrong, fix the predicate, not the command |
| Find a checkout or understand project boundaries | `projects.md` |
| Queue, inspect, resume, debug, or clean up TPU jobs | `infra.md` |
| Change VLM training, checkpointing, resume, or eval code | `vlm_training.md` |
| Upload VLM datasets, audit adapters/coordinates, prepare eval mirrors | `vlm_data.md` |
| Decide which VLM benchmark number to report, or a score looks wrong | `vlm_metrics.md` |
| Log WandB results into the experiment spreadsheet | `spreadsheet.md` |
| Manage a long-running experiment loop | `research.md` |
| Run or interpret a weight-sharing optimizer experiment (normalize-then-sum) | `research/normalize_then_sum.md` |
| Write a paper deep-reading report | `paper_reading.md` |
| Lay out or debug a report's HTML/PDF rendering | `paper_rendering.md` |
| Reclaim shared NFS or local disk space | `storage.md` |
| Decide whether a copy or artifact is complete, or find every writer of an output path | `storage.md` |
| Read, draft, or send mail from the MIT account | `email.md` |
| Research idea page | `research/normalize_then_sum.md`|

## Global Rules

Most rules are owned in full by the page named beside them. These are the ones
expensive enough to state twice.

**With the user, write plain language, not agent jargon.** Converse in Chinese,
and write wiki pages and code artifacts in English; paper reports are the
exception (`paper_reading.md`). Lead with the outcome, and say it the way you
would to a colleague who does not read your logs. Name what happened rather than
the internal state name for it. Spell out an identifier the first time it
appears, but keep literal names (a job id, a TPU name, a zone), because they are
what the user greps for.

**Push only when the user's current request explicitly asks for a push.**

**Never destroy the user's work.** Preserve user changes: never revert,
overwrite, or clean a dirty worktree as collateral work. Before deleting shared
or local data, identify the filesystem, owner, active references, and recovery
path, and use a manifest for shared or bulk deletion (`storage.md`).

**Debug locally, then with one small remote run, before a real run.** After any
large code change, run the checkout's local debug runner (`local_debug.sh` in the
VLM checkouts), then one small remote debug run (`debug_remote.sh`) on a card you
own, and only then queue through `infra`. A remote round trip costs a staged
snapshot, a queue wait, and a card, and most of what dies there dies locally too
(`engineering.md` Chapter 2).

**Keep compute next to its data.** Avoid cross-region or cross-zone data and
checkpoint access; if payload access is necessary, first prove compute and
storage locality. Cross-region copying costs money and is off by default; only a
one-time small copy, such as one checkpoint, is allowed (`infra.md`).

**Treat external writes as transactions.** Establish identity and target,
validate assumptions, write the smallest scope, then read back the result
(`engineering.md` §External writes are transactions; mail in `email.md`).

**Re-read the sheet before logging a result.** Read the tab's header and
neighboring rows every time: the layout drifts, and a stale column map files a
number in the wrong place without an error. Place the row before filling it, keep
cells short, and treat formatting as part of the result (`spreadsheet.md`).

**Repository-local instructions own code semantics.** Follow a repository's own
`AGENTS.md` or `CLAUDE.md` for project-specific code semantics. The shared infra,
locality, storage, and external-write rules here supersede stale operational
sections in old project notes. Surface any remaining conflict rather than
guessing.

## Evidence Order

**When facts disagree, prefer this order:**

1. The user's current request.
2. Current repository code and repository-native docs.
3. Live infra state, logs, WandB, and the spreadsheet.
4. The core guides in this folder.
5. `archive/`, which is historical evidence only.

**To claim that X works, is allowed, or fits, perform X once; do not query a
status that describes X.** A status query usually measures the neighboring thing,
and it fails in the expensive direction, because it looks like supporting
evidence. The hard part is stating what the claim actually asks.

| The claim | The status query that looks right | What it actually measures |
|---|---|---|
| This slice will fit the model | Total HBM across the slice | Per-chip HBM binds when weights are replicated; the total binds only under model parallelism |
| This card is free | `tou` shows it `IDLE` | A visibility view, not the infra owner, the tmux window, or a remote process holding the devices (`infra.md`) |
| That agent or job is still alive | A process holds its log, or a dashboard says it is running | That some process writes a file; dashboards go stale and are not authoritative |
| My mail was sent | The EWS request returned HTTP success | That the service accepted a request, not that the item exists; read it back (`email.md`) |
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

## Maintaining Memory

**Record a rule only when a future agent cannot cheaply infer it from code, or
when violating it has a meaningful cost.** `memory.md` owns the full model and
the rewrite procedure; this is the short list.

- Keep core guides short and decision-oriented. Give each fact one owner, and point at it from everywhere else by file name.
- Write the rule, not the incident. Keep the one clause of evidence that makes it credible; forensics go to `archive/` or git history.
- Replace stale facts instead of appending incident diaries or corrections. Never record live state (mirror completeness, job status) in a guide; record how to verify it.
- Lead each section with its rule in bold, and put a caveat inside the sentence it qualifies, never in the paragraph after it.
- Write plain sentences, not a house dialect. No literary metaphor, no aphorism, no bolding a whole paragraph, no em-dash chains, no 40-word sentences. Prefer a table to five parallel bullets.
- Put dated audit evidence (scan counts, validation numbers, status snapshots) under `archive/audits/` and keep only the derived rule plus a pointer in the guide. Delete audit snapshots once they are too old to be evidence.
- Preserve detailed or superseded text under `archive/` when it remains useful for forensics. Never route a new agent there by default.
