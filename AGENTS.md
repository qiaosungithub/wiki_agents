# Workspace Memory

Durable rules for working under `/usr/local/google/home/qiaos/work`. Current
code, live state, and the user's request always outrank this folder.

## Start Here

1. This file, then `engineering.md` — the working discipline, for any task.
2. `projects/README.md` — identify the checkout, its category, and its guide.
3. Only the guides the router below names.
4. Then the actual code, git state, and live system.

## Layout

Files in this directory apply to every task; subdirectories are read on demand
and each has a `README.md` index.

| Path | Owns |
|---|---|
| `engineering.md` | Method: how to verify, diagnose, port, and report. |
| `jobs.md` | Queue, inspect, resume, debug a cluster job. |
| `storage.md` | Where data lives, reading it fast, cleaning up safely. |
| `tpu_reference.md` | Accelerator names, memory, legal shapes, ratios. |
| `gpu_on_borg.md` | Run an NVIDIA GPU job on Borg via `tpu enqueue` (CUDA build, NCCL, tiers, traps). |
| `gcp_gpu_ssh.md` | SSH to the GCP GPU VMs (viscam-cloud); OS Login vs metadata keys. |
| `monitoring.md` | The monitor role: watcher, DEAD/idle alerts, handoffs, escalation. |
| `projects/` | Per-checkout semantics and boundaries. |
| `research/` | Running experiments; logging results. |
| `reports/` | Writing and rendering paper reports. |
| `infra/` | Allocator, market, and CLI internals, when `jobs.md` falls short. |
| `tools/` | Executable helpers (price caps); prose elsewhere. |
| `handoffs/` | Pointer only — handoff docs live in `~/work/.monitor_watch/handoff_bodies/`. |
| `archive/` | History. Never routed to by default. |

## Topic Router

| Task | Read |
|---|---|
| Anything, before you start | `engineering.md` |
| **After a large code change, before submitting a job** | `engineering.md` §Debug Locally On CPU Before You Spend A Remote Round Trip |
| Find a checkout or its boundaries | `projects/README.md` |
| Queue, inspect, resume, debug a job | `jobs.md`, then the project guide |
| **Resume a job / write anything that passes a checkpoint to a job** | `jobs.md` §The `LOAD_FROM` Contract |
| Submit a job or a batch (default `tpu enqueue` + serial `tpu build-worker`; auto cell / `--metro`) | `jobs.md` §The Submission Queue In One Screen |
| A CPU-only batch job will not schedule | `jobs.md` §Requirements And Runtime |
| Choose a cell (now auto-picked); preflight before packaging | `jobs.md` §Choosing Where To Run |
| A job will not schedule; capping spend | `infra/quota_market.md`, `tools/limit_order.sh` |
| Change the `tpu` CLI or its daemon | `infra/tpu_cli.md` |
| TPU codename, HBM, legal shape, equivalence | `tpu_reference.md` |
| GPU arch token, NVLink domain, legal shape, card code | `tpu_reference.md` §NVIDIA GPUs |
| **Run a GPU job on Borg** (`tpu enqueue --tpu_type=h100-8`); CUDA build, NCCL, device_count==0, GPU preemption | `gpu_on_borg.md` |
| SSH to a GCP GPU VM; `Permission denied`; OS Login vs metadata keys | `gcp_gpu_ssh.md` |
| **Choose an accelerator family**; a preemptible slice will not hold | `research/accelerator_choice.md` |
| Place data or checkpoints; copy or upload | `storage.md`, then the project guide |
| Pick a cell/metro for a v7 run | `research/v7_storage_placement.md` |
| **Map a cell to its metro or its CNS bucket**; add a cell to any such table | `storage.md` §Never Hand-Maintain A Cell -> Metro -> Bucket Table |
| **Copy, move, or hand off a checkpoint**; resume across metros | `storage.md` §A Checkpoint Path Is An Opaque String |
| Read a distributed path interactively | `storage.md` §Distributed Reads |
| **CitC/srcfs is dropping writes**; `CreateSnapshot failure`; a staging rsync that never converges | `storage.md` §Before Blaming CitC For Dropping Writes |
| A write fails, or a job produced 0-byte logs | `storage.md` §An Over-Quota Cell Looks Like A Broken Program |
| Resume skips work, or a 0-byte file counts as done | `storage.md` §Existence Is Not Completeness |
| Reclaim local disk, or prune checkpoints | `storage.md` §Local Disk Cleanup, §Checkpoints Are The Default Reason A Cell Fills Up |
| Manage a long experiment; tracker evidence | `research/README.md` |
| Build or verify a multi-GB artifact on distributed storage | `storage.md` §Building A Multi-Gigabyte Artifact |
| A big write is silently truncated or keeps restarting | `storage.md` §Two Writers On One Output Path |
| A data-movement job: workstation or cluster? | `jobs.md` §Where The Storage CLI Exists |
| A job says `RUN` but produces nothing | `jobs.md` §`state: RUN` Is Not Evidence |
| Write a checker, or a verification keeps saying OK | `engineering.md` §A Test That Cannot Fail |
| **Log a result to the spreadsheet**; find a chart | `research/result_logging.md` |
| **Read a job's curves / harvest `train/*` from the workstation**; the urge to write "the workstation cannot read the datatable" | `research/result_logging.md` §Reading The Curves From The Workstation |
| Write or render a paper report | `reports/README.md` |
| **The workstation is swapping / VSCode-SSH keeps disconnecting**; reclaim idle blaze servers | `engineering.md` §Diagnose From Evidence, Not From The Most Available Story, `monitoring.md` §Memory And Disk Wake Criteria |
| **Monitor a fleet of autonomous runs**; watcher, handoffs, DEAD/idle alerts | `monitoring.md` |
| A watched run shows DEAD/500; hand a heavy line to a fresh session | `monitoring.md` |
| Monitor got a request mid-task; track it so it isn't dropped | `monitoring.md` §Track Every Request In The Todo List |
| Write a handoff doc; retire an old session (kill its worker) | `monitoring.md` §Handoffs: Let The Line Summarize Itself |
| **Where to put / find a handoff doc** (`~/work/.monitor_watch/handoff_bodies/`) | `handoffs/README.md` |
| `EqR` / `EqR-jax` | `projects/eqr_jax.md` |
| RNN unroll optimizer / adding problem / gradient propagation science line | `projects/rnn_unroll_adding.md` |
| VLM training, data, benchmark reporting | `projects/vlm_training.md`, `projects/vlm_data.md`, `projects/vlm_metrics.md` |
| **The amply gateway is down**; `amp new` worker dies at `os.getcwd()`; `amply-launch` prints nothing | `projects/local_agent_cli.md` §Restarting The Amply UX Server |
| Agent web app, or a local agent CLI | `projects/agent_web.md`, `projects/local_agent_cli.md` |

## Global Rules

Each rule below is enforced in full by the guide named beside it. These are the
ones expensive enough to state twice.

**With the user — write plain language, not agent jargon.** Converse in Chinese;
write artifacts in English, except paper reports (`reports/README.md`). Lead
with the outcome, and say it the way you would to a colleague who does not read
your logs. Name the thing that happened rather than the internal token for it:
"the job never started" beats "BUILD_REQUESTED never transitioned". Spell out an
identifier the first time it appears, keep literal names (`PROD`, an XID, a cell)
because they are what the user greps for, and cut the rest. §Maintaining Memory
carries the same rule for what you write into these files.

**Delegating work: default to a NEW amply session, not a sub-agent.** When the
user asks to "open a session", "hand this off", or otherwise delegate a task,
the default is a brand-new top-level amply run (equivalent to `amp new <name>`),
NOT `spawn_*` sub-agents. Launch it as a chat-only run with an empty task and a
descriptive title via `/tmp/launch_chatonly_run.py "<workdir>" "<title>"` (POSTs
`/api/run/new`), then inject the task/handoff over the chat channel
(`POST $DB/chat/send?run_id=<RID>`). Reserve `spawn_*` sub-agents for the
monitor's own short read-only fan-out. Only skip the new-session default if the
user explicitly asks for a sub-agent.

**Never destroy the user's work.** Do not revert, overwrite, or clean a dirty
worktree as collateral. Before deleting anything shared, identify the
filesystem, owner, active references, and recovery path; use a manifest for bulk
deletion (`engineering.md` §External Writes Are Transactions).

**Committing.** git push is your friend. You can push regularly, but need to be
careful which branch to push.

**Debug locally on CPU first.** After any large code change, run the whole path
(training step, logging, visualization, checkpoint save/restore, online and
offline eval) on CPU with the repo's `local_debug` config and
`scripts/local_debug.sh` before spending a remote round trip. Remote debugging
is slow, and most of what dies on the accelerator dies on a workstation too
(`engineering.md` §Debug Locally On CPU Before You Spend A Remote Round Trip).

**Jobs.** On this SHARED workstation, submit through `tpu enqueue` plus one
serial `tpu build-worker`; that is the default that dodges the concurrent-build
zombie XID. Use `tpu queue` one-shot only when no other build is in flight.
Never call `xm launch` / `xmanager launch` directly (`jobs.md` §Submission
Contract).

**BATCH tier is EVAL-ONLY.** Every TRAINING job passes `--tier=PROD` explicitly;
`BATCH` is only ever for eval jobs. `BATCH` is a paying best-effort tier: it
bills the group, it is not the free option, and any PROD demand preempts it the
instant a slot is contested. A training run on BATCH is silently starved and
still costs. Never train on BATCH (`jobs.md` §Requirements And Runtime).

**A chip count is not a size.** Per chip, `v7 = v6p ≈ 2.17x v6e ≈ 4.34x v5p ≈
7.23x v4 ≈ 10.09x v5e`, so matching a `v6p-16` needs a `v6e-32`. Asking for
`v6e-16` silently buys HALF the compute, and the run is then compared as if the
hardware were equal. Do not round these ratios: rounding is the same mistake as
matching on chip count, one order of magnitude smaller. `tpu route --power=`
does the arithmetic, and `tpu_reference.md` owns the table (both are generated
from `router.py::_V5P_MULTIPLIER`; never hand-copy a third version).

**Storage.** Keep compute and storage co-located; a job far from its data is
killed by the pruner, not merely slowed. Never move Type 1 payloads across
regions (`storage.md`, `projects/README.md` for the category).

**Cell -> metro -> bucket comes from one measured table**, `cell_locality.py`
(seeded from `mach_locality`, regenerable via `remeasure_cell_locality.py`).
Never hand-write another copy and never guess. A fallback that returned the cell
name as its own metro made `--metro` silently drop valid cells (it reads as "no
capacity"), and a `_DEFAULT_BUCKET` fallback put a job's writes a continent away
until the pruner deleted it. Resolve buckets by metro, not by cell, and make an
unknown cell fail closed (`storage.md` §Never Hand-Maintain A Cell -> Metro ->
Bucket Table).

**A checkpoint path is opaque; four shapes coexist**, including a torch
`step_<N>.pt` that is a FILE, not a directory. Replay the producer's own string
byte for byte; appending or stripping `/state` breaks a family. Read a
checkpoint from anywhere, but write only to local storage: a training loop
writing cross-metro is ~94x slower, drops duty cycle under the 0.20 floor, and
the pruner deletes the job mid-run (`storage.md` §A Checkpoint Path Is An Opaque
String).

**Resuming: pass the checkpoint in the env var `LOAD_FROM`, verbatim.** Never
via a config key, because which key it lands in differs per family, so writing
the key keeps working on most lines and silently cold-starts the rest. Never
normalize the path either, because four incompatible shapes coexist, including a
torch `step_<N>.pt` that is a FILE, not a directory. Point it at the leaf, and
clear it once the job writes its own first checkpoint; a pinned `LOAD_FROM`
overrides auto-resume forever and reads as training instability. Leave
`CHECKPOINT_BUCKET`, where the job writes, alone. Reading a checkpoint across a
metro is survivable; writing across one gets the job deleted by the pruner
(`jobs.md` §The `LOAD_FROM` Contract).

**Logging results.** Re-read the tab's header and neighboring rows every time;
layout drifts and a stale column map mis-files a number without erroring. Place
the row before filling it, keep cells short, and treat formatting as part of the
result (`research/result_logging.md`).

**Project-local instructions.** A repository's own `AGENTS.md` / `CLAUDE.md` is
authoritative for its code semantics. The shared infra, storage, and
external-write rules here supersede stale operational sections in old project
notes; surface a conflict rather than guessing.

## Evidence Order

The user's request, then current code and native docs, then live infra state and
logs, then these guides, then `archive/` (history only).

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

## Maintaining Memory

**Record a rule only when a future agent cannot cheaply infer it from the code,
or when violating it has a real cost.** Everything else dilutes what matters.

- **Write the rule, not the incident.** Keep the one clause of evidence that
  makes it credible; forensics go to `archive/`, or to git history.
- **Prefer the abstract statement.** A note that only makes sense for one paper
  or one job id belongs in a project guide or the archive.
- **One canonical owner per rule**; everyone else points at it by file name.
- **Replace stale facts; never append a diary.** No "fixed on <date>", no live
  state, no source line numbers, no job ids. Record how to verify instead.
- **Lead a section with its rule in bold.** A reader who stops after the first
  sentence must not be misled.
- **Put the caveat inside the sentence it qualifies, never in the paragraph
  after it.** People quote and act on the bold claim alone, so a qualifier
  parked downstream — "but it may also be X", "(unverified)" — is reliably lost
  in the first retelling, and what survives is more confident than what you
  wrote. When a finding has two branches, name both in one clause so that
  whichever half is copied still carries the other.
- **Prefer a table to five parallel bullets.** Delete audit snapshots once they
  are too old to be evidence.
- **Write plain sentences, not the house dialect.** No literary metaphor, no
  aphorism, no bolding a whole paragraph, no em-dash chains, no 40-word
  sentences. One bold phrase per section, for the rule. This is the same
  standard as the user-facing one above, and it is why the guides read the way
  they do.
- **When a fact stops being true, delete it; do not append a correction.** A
  note that says "X, but actually now Y" makes the reader hold both, and the
  wrong half travels just as far. Cut what is dead: git history is the archive
  (`archive/README.md`).
