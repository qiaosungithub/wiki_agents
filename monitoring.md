# Monitoring Autonomous Runs (the monitor role)

How to be the **monitor**: one long-lived chat session (`chatty-bot`) that watches
a fleet of independent autonomous `amply` runs on behalf of the operator, keeps
them healthy, and hands lines off to fresh sessions when their context gets heavy.
`jobs.md` owns the cluster; `storage.md` owns data; this file owns *watching the
agents that use them*. A monitor writes almost no research code — its job is
liveness, coordination, handoffs, and escalation.

The monitor is spawned fresh each turn; the event stream is the only memory the
harness guarantees. Everything durable lives on disk — see §Live Memory.

## The Monitor Owns One Directory: `~/work/.monitor_watch/`

**Keep every monitor asset in ONE version-agnostic directory, never in `/tmp`
and never in a name with a version number.** History: the watcher lived in
`.monitor_v14_watch/` across many monitor generations; a `v14` in the name reads
as stale and an operator eventually `rm`'d it mid-shift, taking the death
detector down. The current home is `~/work/.monitor_watch/` — do not re-version
it. Layout:

| Path | What |
|---|---|
| `watch.py` | Death + idle detector, cron-run every 10 min. |
| `watch.sh` / `heartbeat.sh` | Cron entry wrappers (set `HOME`, `AMPLY_RUN_ID`, exec python). |
| `runs.txt` | The watched lines: `<name> <full-run-id>`, one per line. |
| `state_<name>.json` | Per-line persisted state (phase, dead_streak, idle_since). |
| `AGENT_STATUS.md` | The live-memory file (see §Live Memory). |
| `tools/` | The cross-run CLIs (probe/lastmsg/handoff). Back them up here. |
| `handoff_bodies/` | Saved handoff docs, so a handoff survives a `/tmp` wipe. |

`/tmp` is a tmpfs and is shared with other users' dead-process litter; anything
you need after a reboot or another user's cleanup must be under `~/work`.

## Take Over In A Fixed Order

On inheriting the role from a prior monitor, before anything else:

1. Read `~/work/wiki_agents/AGENTS.md`, then the prior monitor's handoff doc.
2. **Re-point the watchers at your own run-id.** `heartbeat.sh`, `watch.sh`,
   `watch.py` all hard-code `AMPLY_RUN_ID`; `sed` the old id to yours or the
   heartbeat wakes the wrong (dead) session and you run blind.
3. **Rename the cron locks** (`monitor-vN-*` → your own) so `crontab -l` is
   legible and two monitors never share a lock.
4. `crontab -l | grep monitor` — confirm both lines exist (heartbeat `*/30`,
   watch `*/10`) and point at `.monitor_watch/`.
5. Self-test notify: `~/.amply/bin/amply_notify <your-session> "takeover ok"`.
   You should receive it in your own stream.
6. Baseline sweep all lines; write `AGENT_STATUS.md`.

## Maintain A Live-Memory File Every Turn

**Your context is compacted; only `~/work/.monitor_watch/AGENT_STATUS.md`
survives.** Write it as a past-tense narrative and overwrite it each turn: the
9-line status table (tail → semantic state → health), the handoff ledger (which
line went to which new run-id, what's left), open decisions awaiting the
operator, the memory/disk readings, and the gotchas hit this shift. A monitor
that only keeps state in context *will* forget it after the first compaction.
The lesson is earned: a prior monitor stopped updating it after one compaction
and coasted on luck for hours.

## The Watcher: Death, Idle, And Their False Positives

`watch.py` probes each line's `chat_status` every 10 min and notifies the
monitor. The design is mostly a catalog of false positives that had to be
suppressed — keep every guard:

- **Probe by FULL run-id, not by list search.** The server's `list_runs` is
  hard-capped at ~50 rows regardless of `limit=`. An older line drops off the
  list and a list-based probe reports it DEAD forever. `runs.txt` therefore
  stores full run-ids and `watch.py` calls `chat_status(full_rid)` directly. The
  `/tmp` helper tools were patched the same way (a selector with ≥2 dashes is
  treated as a full id).
- **DEAD needs two consecutive dead ticks.** A single `chat_status` timeout is
  almost always the chat sidecar queuing under load at a cron boundary, not a
  dead worker. Requiring two ticks (~20 min) removed a whole class of 3am false
  alarms. On any DEAD alert, re-probe with `tools/probe10.py` before acting;
  `runstat=ongoing` means it was a false positive — **never blind-restart a live
  run.**
- **HTTP 500 is not death.** A 500 on `chat_status` means the gateway is up but
  choked on that one run (see §Gateway Version Skew). Treat it as inconclusive:
  skip the tick, do not bump `dead_streak`.
- **Gateway-down gates the whole tick.** If `list_runs` itself is unreachable
  (operator restarting the server), every line would look dead. `watch.py`
  preflights gateway health and skips the entire tick rather than emit a
  fleet-wide DEAD storm.
- **Idle is a recurring digest, not a per-line one-shot.** A session that stops
  working is either waiting on a decision or stuck; both need surfacing. One
  consolidated `💤 idle 巡检` notification lists every idle line and how long
  it's been idle (`idle_since` persisted in state), and it **re-fires every
  tick** until the line goes active — so a line parked for hours keeps nagging.
  Tune `IDLE_ALERT_SECS` (0 = surface from the first idle tick).
- **Detect activity by a monotonic step counter, NOT the instantaneous
  `working` flag.** `chat_status.working` is true only *during* a turn; a turn
  that starts and finishes between two 10-min polls is invisible, so a line that
  replies every few minutes reads as permanently idle and the idle clock never
  resets (a real false-idle bug hit `dfw` this way — it answered the operator
  but every tick sampled `working=False`). Use `chat_status.chatbot_current_step`
  (increments once per turn): if it advanced since the last tick, the line WAS
  active between ticks. Treat `working OR step-advanced` as active. General rule:
  poll-based liveness must key off a monotonic counter's delta, never an
  instantaneous busy flag.

## Cross-Run Communication

`send_message` only reaches sessions in your *own* run. The watched lines are
*separate* runs, so talk to them through the chat API via the helper CLIs in
`.monitor_watch/tools/` (all import `agent-island/claude-amply.py`'s
`AmplyClient`):

| Tool | Use |
|---|---|
| `probe10.py <id>` | One line's status (working / live / nmsg). DEAD re-probe. |
| `lastmsg.py <id> [n]` | Last n messages of a run. Read what a line is waiting on. |
| `getmsg_full.py <id>` | Full text of a run's last message. |
| `do_handoff_generic.py <body_file> <title>` | Start a new chat run, send body, title it. |

Pass a **full run-id** to bypass the list cap. Raw fallback when a helper is
down: `curl -s -X POST "<dashboard_url>/chat/send?run_id=<RID>"
--data-urlencode "content@FILE"` (the gateway 500s intermittently — retry).

`amply_notify <session-id>` takes the **chat session name** (`chatty-bot`), NOT
a run-id — passing a run-id fails with `Session not registered`. See AGENTS.md
for the local-copy caveat (`~/.amply/bin/amply_notify`).

## Handoffs: Let The Line Summarize Itself

When a line's context gets heavy (slow, repetitive, tool calls timing out),
hand it to a fresh session. **The retiring session writes its own handoff doc —
it is far more accurate than a monitor writing it from the outside.** Protocol:

1. Message the line: write a **self-contained** doc (every run-id / XID / cell /
   cns path / branch / commit / workspace path spelled out — a fresh agent has
   zero context), and paste the full text back in its next reply.
2. Grab the pasted body (`lastmsg.py` / `chat_messages`), save under
   `handoff_bodies/`.
3. Fix any stale references in the body (e.g. the prior monitor's run-id → yours).
4. Prepend a short framing header ("you are the new session for line X;
   a monitor watches your health; start from §N").
5. `do_handoff_generic.py <framed> "<title> (handoff vN)"` → note the new run-id.
6. Tell the old session it's retired + the new run-id.
7. Update `runs.txt` (name → new full id), delete the stale `state_<oldname>.json`,
   update `AGENT_STATUS.md`.

**Hand off ONE line at a time**, and only when the line's current exchange with
the operator has closed — interrupting a live decision loop loses work. A doc
written minutes ago can already be stale (a just-launched XID, a merge that
landed); patch it before shipping.

**Concurrent launches that share a build root corrupt each other — route a batch
through the serial build-worker, do not hand-orchestrate it.** Two `blaze` builds
running at once under one checkout race on the **blaze output layer**: `blaze-bin`'s
second symlink hop (`blaze-out → /google/obj/workspace/namespace/<uuid>/blaze-out`)
is republished by every build under the same checkout root, so one build's outputs
land in a namespace the other isn't looking at → a `found []` zombie work-unit
(XManager snapshots the code but blaze produced no output for the target; this bit
a parallel elt+parcae v6e migration). A second failure mode compounds it: a burst
of concurrent stage-writes drains the CitC CreateSnapshot token bucket →
truncated stagedir, `.par` crash. **Neither is a stagedir-name collision** — that
was fixed separately (`eqr_run_<ts>_<6hex-urandom>` + atomic `mkdir`, after the
2026-08-17 "4 XIDs → 1 stagedir" incident).

**The fix is now a tool, not a monitor chore: `tpu build-worker` (serial
build-worker).** A batch is `tpu enqueue`'d and one worker drains it one build at
a time (a durable `flock`'d BUILDING lock guarantees ≤1 build in flight even
across processes), curing both failure modes at once. So when a line wants to
launch a **sweep / multi-arm batch**, tell it to use the build-worker
(`../jobs.md` §Launch a batch), not to fan out `setsid` launches. The worker also
self-limits (bad `--workdir` or repeated `found[]` → the job goes HELD, not an
infinite churn), so it is safe to leave draining unattended.

**What the monitor still owns:**
- A **single line hand-launching one arm** (the common case) needs no worker —
  its own guard (`tpu_queue_guarded_wsaware.sh`, 5 gates) is enough; just don't
  green-light two *different* lines to build in the *same checkout* at the same
  instant. Simultaneous "go" messages into one checkout are still a coordination
  hazard.
- **Different checkouts** (different `output_base`) genuinely don't collide, so
  parallel go's across distinct checkouts are fine.
- When in doubt, prefer the build-worker: it makes "serial" the default instead
  of something you enforce by timing green-lights.

## Deciding Vs Escalating

The operator runs a monitor precisely so they are *not* asked to confirm every
step. **Exercise judgment; escalate only real cost or real risk.**

- **Just do it** (the line is only asking permission for its own recommendation):
  a zero-cost / reversible / already-authorized action — a `bid=0` canary to
  probe a scheduling window, a `git commit`/`push` a line is treating as
  blocking, a low-risk cherry-pick of the operator's own verified commit. Tell
  the line the scope you're authorizing and why.
- **Capacity moves and zombie cleanup are pre-authorized.** This operator has
  standing approval ("这种事情我都同意") for: migrating a stuck job to an
  **algo-equivalent, co-located** alternative (e.g. v6p-32 → v6e-64 at a cell in
  the same metro as the data), and cancelling a **zombie or superseded** job (a
  baseline a line has proven redundant, a slice thrashing with zero net progress
  for hours). Just relay the vetted plan and let the line execute. Do NOT re-ask
  each time.
- **Escalate to the operator**: real spend (adding bid / reservations),
  cross-region data moves, a genuine research fork, or destroying work that
  isn't clearly superseded. When several such decisions pile up, batch them into
  one screen rather than dripping them out.
- **Never** blind-restart a live run, `rm` shared state, or add memory pressure
  by spawning agents when memory is tight.

## Verify A "Harmless" Cleanup Before Doing It

**A prior note calling something a dead orphan is a hypothesis, not a fact —
re-verify against the live system.** A handoff flagged `/tmp/claude-<pid>` (33G,
tmpfs) as a dead-process orphan safe to delete. It was not: a live `claude`
session in a `tmux` window had `--resume`d the same session UUID and was
actively writing there. `lsof +D <dir>`, `fuser`, and scanning `/proc/*/cwd`
before any `rm` caught it. The tmpfs pressure was real; the deletion was not
safe. Distinguish the symptom from the fix.

## Gateway Version Skew (persistent 500 on new runs)

**Symptom:** `ar <run>` / `chat_status` returns HTTP 500 for *newly created*
runs while old runs are fine. **Cause:** the running gateway binary predates an
event type the newer worker writes (e.g. a `todo` event) — the read path
deserializes every event and throws `ValueError: Unknown event type` on the new
one, 500ing `/api/chat` and `/api/events`. The run itself is healthy
(`chat_messages` still reads it); only the status/attach path is broken.
**Fix is the operator's:** rebuild + restart the gateway. The monitor's job is
to *diagnose it precisely* (find the traceback in the server INFO/ERROR log
under `/usr/local/google/tmp/amply.*.log.*`), report, and NOT restart the shared
server itself. After any gateway restart, **broadcast to every line**: notify
delivered during the outage was dropped and never retried, so each agent should
re-verify the job/milestone it was waiting on directly and restart its own
watcher (which re-resolves the worker address).

## Memory And Disk Wake Criteria

The box runs hot with many concurrent lines. **A single tight reading is noise;
wake the operator only on a sustained signal.** Steady state seen in practice:
`available` 12–35G, `swap used` 70–86G, zero OOM-kills (self-heals in minutes).
Escalate only if `available` < 10G on 3–4 consecutive probes with nonzero
`si/so`, or `swap used` breaks ~84G without receding, or the OOM-killer fires.
Each large build (eval/canary/mirror) spikes memory for 1–2s — do not panic.
`/tmp` is tmpfs (counts against RAM): each heartbeat, `df -h /tmp`; over ~90%,
`du -sh /tmp/* | sort -rh | head` and report (never `rm -rf /tmp/*` — the
monitor's own tools historically lived there).

## Subagents For Fan-Out

For a bounded read-only investigation across the fleet (e.g. "are jobs stuck,
and why"), spawn a `standard_agent` with `workspace_mode='inherit'` and a strict
read-only charter (no job submit/cancel, no code edits, no further spawns, no
cluster load). Have it write a report to its artifact dir and reply with the
key findings. Then **reconcile its conclusions against the lines themselves** —
a report flagged a coconut job as "zero-progress stuck" when the line had
*deliberately* migrated to a healthy replacement and was about to cancel the old
one. The subagent sees jobs; the line knows intent.
