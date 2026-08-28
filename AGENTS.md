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
| `archive/` | History. Never routed to by default. |

## Topic Router

| Task | Read |
|---|---|
| Anything, before you start | `engineering.md` |
| Find a checkout or its boundaries | `projects/README.md` |
| Queue, inspect, resume, debug a job | `jobs.md`, then the project guide |
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
| Read a distributed path interactively | `storage.md` §Distributed Reads |
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
| Write or render a paper report | `reports/README.md` |
| **Monitor a fleet of autonomous runs**; watcher, handoffs, DEAD/idle alerts | `monitoring.md` |
| A watched run shows DEAD/500; hand a heavy line to a fresh session | `monitoring.md` |
| Monitor got a request mid-task; track it so it isn't dropped | `monitoring.md` §Track Every Request In The Todo List |
| Write a handoff doc; retire an old session (kill its worker) | `monitoring.md` §Handoffs: Let The Line Summarize Itself |
| `EqR` / `EqR-jax` | `projects/eqr_jax.md` |
| RNN unroll optimizer / adding problem / gradient propagation science line | `projects/rnn_unroll_adding.md` |
| VLM training, data, benchmark reporting | `projects/vlm_training.md`, `projects/vlm_data.md`, `projects/vlm_metrics.md` |
| Agent web app, or a local agent CLI | `projects/agent_web.md`, `projects/local_agent_cli.md` |

## Global Rules

Each rule below is enforced in full by the guide named beside it. These are the
ones expensive enough to state twice.

**With the user** — Converse in Chinese; write artifacts in English, except
paper reports (`reports/README.md`). Lead with the outcome; stay concise and
plain.

**Delegating work — default to a NEW amply session, not a sub-agent** — When
the user asks to "open a session", "hand this off", or otherwise delegate a task,
the default is a brand-new top-level amply run (equivalent to `amp new <name>`),
NOT `spawn_*` sub-agents. Launch it as a chat-only run with an empty task and a
descriptive title via `/tmp/launch_chatonly_run.py "<workdir>" "<title>"` (POSTs
`/api/run/new`), then inject the task/handoff over the chat channel
(`POST $DB/chat/send?run_id=<RID>`). Reserve `spawn_*` sub-agents for the
monitor's own short read-only fan-out. Only skip the new-session default if the
user explicitly asks for a sub-agent.

**Never destroy the user's work** — Do not revert, overwrite, or clean a dirty
worktree as collateral. Before deleting anything shared, identify the
filesystem, owner, active references, and recovery path; use a manifest for bulk
deletion (`engineering.md` §External Writes Are Transactions).

**Committing** — git push is your friend. You can push regularly, but need to be
careful which branch to push.

**Jobs** — On this SHARED workstation, submit through `tpu enqueue` + one serial `tpu build-worker` (the default that dodges the concurrent-build zombie XID); `tpu queue` one-shot only when no other build is in flight. Never call `xm launch` / `xmanager launch` directly (`jobs.md` §Submission Contract).

**BATCH tier is EVAL-ONLY** — Every TRAINING job passes `--tier=PROD`
explicitly; `BATCH` is only ever for eval jobs. `BATCH` is a *paying*
best-effort tier (it bills the group, it is not the free option), and any PROD
demand preempts it the instant a slot is contested — so a training run on BATCH
is silently starved AND still costs. Never train on BATCH (`jobs.md`
§Requirements And Runtime).

**A chip count is not a size** — Per chip, `v7 = v6p ≈ 2x v6e ≈ 4x v5p ≈
8x v4`, so matching a `v6p-16` needs a **`v6e-32`**. Asking for `v6e-16`
silently buys HALF the compute, and the run is then compared as if the hardware
were equal. `tpu route --power=` does the arithmetic (`tpu_reference.md`).

**Storage** — Keep compute and storage co-located; a job far from its data is
killed by the pruner, not merely slowed. Never move Type 1 payloads across
regions (`storage.md`, `projects/README.md` for the category).

**Logging results** — Re-read the tab's header and neighboring rows **every
time**; layout drifts and a stale column map mis-files a number without
erroring. Place the row before filling it, keep cells short, and treat
formatting as part of the result (`research/result_logging.md`).

**Project-local instructions** — A repository's own `AGENTS.md` / `CLAUDE.md` is
authoritative for its code semantics. The shared infra, storage, and
external-write rules here supersede stale operational sections in old project
notes; surface a conflict rather than guessing.

## Evidence Order

The user's request, then current code and native docs, then live infra state and
logs, then these guides, then `archive/` (history only).

**To assert that X has permission / fits / will be received, perform X once —
do not query a status that describes X.** A status query almost always measures
the *adjacent* thing, and it fails in the most expensive direction: it looks
like supporting evidence. The hard part is not finding evidence, it is stating
what the claim actually asks.

| The claim | The status query that looks right | What it actually measures |
|---|---|---|
| This slice will fit the model | total HBM across the slice | per-chip HBM, when weights are replicated (`model_size=1`); totals bind only under model parallelism |
| I lack membership in a group | `aclcheck` returns `PERMISSION_DENIED` | whether you may *read the ACL* — a sandbox that cannot reach the ACL proxy denies identically |
| This capacity is usable | the router shows the shape `PLACEABLE` | that an availability RPC answered; not the budget gate, the authorization, or preemption |
| That agent still exists | a writer holds its log, or a dashboard says `ongoing` | that some process writes a file; dashboards go stale and are not authoritative |
| My alert reached the on-call | the notify call returned `rc=0` | that *a* worker accepted it — possibly a retired session nobody reads |
| This will never finish / never be released | it is making no progress now, and the ways it could finish are all ruled out | that it is stuck **at this instant** — a very slow counterpart can still return, and ruling out the exits you thought of is not ruling out the ones you did not |

The last row is the trap in its **time** form, and it is the one that reads as a
verdict: the reading is correct, and it is a reading of *now* answering a
question about *later*. Say "I do not know when it will be released", never "it
will not be released" — and when a fix or a fresh sample proves it wrong,
recognise that the observation was never wrong, only its tense. Everything above
it is the trap in its **space** form: the query measured the neighbouring thing.

The `rc=0` row is the general case of that: **a silent success is more dangerous
than a clean failure**, because failure leaves a trace and `rc=0` makes every
check look green. Close the loop at the far end — confirm the message arrived in
the recipient's stream, confirm the job reached `RUNNING` and wrote its own
verdict.

**Then check that the value you read came from the command you ran.** A shell
pipeline reports the exit status of its *last* stage, so `cmd | head` reads
`head`'s success and hides `cmd`'s failure. Capture instead with
`out=$(cmd 2>&1); rc=$?`, or redirect to a file — **`${PIPESTATUS[0]}` is itself
a trap**: any intervening statement, including the `rc=$?` assignment meant to
save it, resets the array. Having performed X is not enough if the reading
instrument measures something else; that mistake survives review, because the
number is real and reproducible.

**A pipe truncates the answer as well as the status.** `| head -N` silently
drops content, and it drops it invisibly — the output still looks complete,
because it was always meant to be several lines. An item that vanishes from a
windowed listing has not necessarily vanished; it may have been pushed out by a
new one. **A disappearance is only evidence once you know the total** — count
first, or read it whole.

**And a failed reproduction only refutes when it reproduces the conditions.**
Running the check somewhere else, or on a shorter timescale than the effect,
turns a refutation into an unrelated success: the same probe against a different
workspace, or a 3-second window against a 30-minute one, cannot see the thing it
claims to rule out. State what the negative result covers, not what it feels
like.

**When someone corrects you, verify the method their correction rests on, not
just its conclusion.** Once a claim has passed through two people who each only
checked the other's *downstream* reasoning, the faulty *premise* is what nobody
re-examines. A self-correcting process beats an infallible one — but only while
each round re-checks premises rather than conclusions.

**Hedging a number does not make it right — a second, independent route to the
same answer does.** "Rough estimate, timestamped, not claiming precision" is a
statement about your confidence, not about the value, and it can sit in front of
a figure that is wrong by a factor of five while making it *read* as measured;
the same holds for a well-formed method list in front of a false conclusion.
Before quoting a number that someone will plan against, derive it a second way
— a different instrument, a different window, a different artifact — and if you
only have the one, hedge the **range** rather than your posture: "about two
hours, from a single six-minute window, so possibly several times that" invites
the reader to check, where "about 2.1 hours (rough)" does not. Beware in
particular a slope measured across a transient: a rate taken during startup,
catch-up or backlog drain is not the steady state, and **a window is long enough
only when it does not consist of a single phase.**

**And when you act on something you were told rather than something you saw, go
back to the source first.** Hedges do not survive relay: whoever passes a
finding along copies the conclusion and drops the "(unverified)", so a claim
gets *more* confident the further it travels from the person who knows how weak
it is. One round trip to the original — did they mark this unproven? — costs
seconds, and is worth it whenever the next step is hard to walk back: editing
shared docs, changing a config, killing something. **Agreement is not
corroboration when it is the same evidence arriving twice**, and neither is it
when several people ran the same incomplete checklist — count distinct methods,
not distinct agreers.

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
