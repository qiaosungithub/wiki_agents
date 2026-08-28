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
and never in a name with a version number.** A prior `.monitor_v14_watch/` read
as stale and an operator `rm`'d it mid-shift, taking the death detector down. The
current home is `~/work/.monitor_watch/` — do not re-version it. Layout:

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
6. Baseline sweep all lines with `tools/recap.py` (§Exhaustive Fleet Recap) —
   it shows who-spoke-last, so any request the prior monitor left unanswered
   surfaces immediately; reply to every `● LINE` before declaring takeover done.
   Then write `AGENT_STATUS.md`.

## Maintain A Live-Memory File Every Turn

**Your context is compacted; only `~/work/.monitor_watch/AGENT_STATUS.md`
survives.** Overwrite it each turn (past-tense narrative): the 9-line status
table (tail → semantic state → health), the handoff ledger (which line → which
new run-id, what's left), open decisions awaiting the operator, memory/disk
readings, gotchas hit this shift. A monitor that keeps state only in context
*will* forget it after the first compaction (a prior monitor stopped updating it
and coasted on luck for hours).

## Track Every Request In The Todo List (mandatory)

**You MUST keep a live todo list via the `todo_write` tool, and the FIRST thing
you do on any operator message you can't finish immediately is append it there.**
The monitor is spawned fresh per turn and compacted often; a request you only
hold in context is a request you will drop the moment you get busy or compact.
The `todo_write` list is re-shown to you in the `[STATUS]` block every turn and
rendered to the operator in their UI, so it is the one place a pending request
is safe and visible to both sides.

The non-negotiable protocol when a message arrives while you are mid-task:

1. **Append first, act second.** Before you return to what you were doing, call
   `todo_write` to add the new request as a `pending` item (resend the whole
   list — the tool is whole-list-replace). Do this even for "I'll get to it in
   a second" — *especially* then.
2. **Then judge urgency:**
   - **Not urgent** → leave your current `in_progress` task as-is, finish it,
     then pull the new item. The new item sits `pending` until you reach it.
   - **Urgent / operator wants it now** → flip your current task back to
     `pending` (it STAYS on the list — you are not abandoning it), mark the new
     item `in_progress`, handle it, then resume the bumped task.
3. **Exactly one `in_progress` at a time**, and mark an item `completed` the
   moment it is done — do not batch completions. An operator reading the list
   must be able to trust that `in_progress` is what you are truly on right now.
4. **Nothing leaves the list until it is done.** A request you answered but
   whose follow-up is still open stays on the list; a request you escalated
   stays `pending` with the blocker noted in its text.
5. **Roll the list over once a batch is fully done.** Nothing auto-clears when
   every item is `completed` — the list just sits there growing. So when the
   whole list is `completed` and a new request arrives, prefer to REWRITE it
   fresh (whole-list replace: send just the new open items, dropping the
   finished batch) rather than letting it accrue forever. The durable
   per-shift history lives in `AGENT_STATUS.md`; the todo list should stay a
   short view of what is outstanding NOW, not an ever-growing ledger.

This is the monitor's contract with the operator: every message they send is
either done or visibly on the list. "I forgot you asked" is the one failure a
monitor is not allowed to have, and the todo list is how you prevent it — it
outlives the context that a bare mental note does not. It is the per-request
companion to `AGENT_STATUS.md` (§Live Memory): that file holds the per-shift
narrative, the todo list holds the outstanding asks.

## The Watcher: Death, Idle, And Their False Positives

`watch.py` probes each line's `chat_status` every 10 min and notifies the
monitor. The design is a catalog of suppressed false positives — keep every guard:

- **Probe by FULL run-id, not list search.** `list_runs` is hard-capped at ~50
  rows regardless of `limit=`; an older line drops off and a list-based probe
  reports it DEAD forever. `runs.txt` stores full run-ids; `watch.py` calls
  `chat_status(full_rid)` directly (the `/tmp` helpers too: a selector with ≥2
  dashes is treated as a full id).
- **DEAD needs two consecutive dead ticks.** A single `chat_status` timeout is
  almost always the chat sidecar queuing under load at a cron boundary; two
  ticks (~20 min) killed a class of 3am false alarms. On any DEAD alert re-probe
  with `tools/probe10.py` first — `runstat=ongoing` = false positive; **never
  blind-restart a live run.**
- **HTTP 500 is not death** — gateway up but choked on that one run (§Gateway
  Version Skew). Inconclusive: skip the tick, don't bump `dead_streak`.
- **Gateway-down gates the whole tick.** If `list_runs` itself is unreachable
  (operator restarting the server) every line looks dead, so `watch.py`
  preflights gateway health and skips the tick rather than storm a fleet-wide DEAD.
- **Idle is a recurring digest, not a per-line one-shot.** One consolidated
  `💤 idle 巡检` lists every idle line + how long (`idle_since` in state) and
  **re-fires every tick** until the line goes active, so a parked line keeps
  nagging. Tune `IDLE_ALERT_SECS` (0 = surface from the first idle tick).
- **Detect activity by a monotonic step counter, NOT the `working` flag.**
  `chat_status.working` is true only *during* a turn, so a turn that starts and
  finishes between two 10-min polls is invisible and a line replying every few
  minutes reads as permanently idle (this false-idle bug hit `dfw`: it answered
  the operator but every tick sampled `working=False`). Use
  `chat_status.chatbot_current_step` (one increment per turn): advanced since
  last tick → active. Treat `working OR step-advanced` as active. General rule:
  poll-based liveness keys off a monotonic counter's delta, never an
  instantaneous busy flag.

## Exhaustive Fleet Recap: Sweep EVERY Line, Not Just The Ones You're Tracking

**Every heartbeat, recap ALL lines in `runs.txt` with `tools/recap.py`; pings
alone are sampling, a recap is a census.** Both watcher alert paths have the
same blind spot: the idle digest only fires for *idle* lines, and the
`awaiting.json` ping only for lines you *explicitly registered*. A line that
posted a request you never registered — or posted it to the *previous* monitor
before a handoff — is invisible: it's working (not idle) and not in
`awaiting.json`. A maze128 line lost a 3-point green-light ask for ~40 min this
way (addressed to the prior monitor, never re-polled).

`recap.py` prints per line: liveness, WHO SPOKE LAST, how long ago, a preview.
Who-spoke-last is the critical column:

- **`● LINE`** — line spoke last, unanswered = **ball in the monitor's court**;
  these silently accumulate unanswered requests. Read + act on every one
  (reply / green-light / no-op) each recap. `recap.py --owed` prints just this set.
- **`○ me`** — monitor/operator spoke last; the line is working or will reply.

Run it each heartbeat and after ANY takeover/handoff — it's cheap (one
`chat_messages` per line) and is what makes "I dropped a session" structurally
impossible rather than luck.

**A recap also catches split-brain:** a line replying to a broadcast *you never
sent* means another monitor is still live (a retiring one whose run hasn't
exited). Reconcile who leads immediately (§Handoffs), stand the other down to
read-only, and fold any action it took into your state so you don't repeat it.

## A Delivered Message Can Still Arrive Broken

**`rc=0` on a send proves a message was accepted, not that it was intact —
an unquoted heredoc evaluates backticks and `$vars` in your own text, and the
send still reports success.** Two instances in one shift, the second inside the
message explaining the first: one shipped a literal `$DOC` where a path should
have been, the other lost three code blocks to command substitution (with a
`command not found` on stderr that nobody was reading). This is worse than a
failed delivery, because a failure leaves a trace. **Always `<<'EOF'` — quote
the delimiter — whenever the body contains a backtick, `$`, or any shell
metacharacter.**

**Never hard-code a run-id as an alert target.** Every watcher pinned to the
previous monitor goes silently mute the moment that run completes, and the
failure is invisible from the sender's side: `amply_notify` returns rc=2
(sidecar gone) or the gateway returns `HTTP 400 ... chatbot is not listening`,
both into a log nobody reads. Discover the target at send time, confirm with a
probe that is not rc=2/3, and spool undelivered alerts to disk so the backlog
survives. A shift where the sentinel worked perfectly and 23 real alerts reached
nobody looks exactly like a quiet shift.

**Find the current monitor by anchoring on the hash: `grep -a "# THIS MONITOR"`.**
Retired rows keep the phrase `(was THIS MONITOR, takeover HH:MMZ)` mid-line, so
the loose `grep -a "THIS MONITOR" | head -1` returns the *oldest* retired monitor
— measured three generations stale. And do not "fix" that with `grep -av "^#"`:
it happens to work, but it filters full-line comments while the interference is
mid-line, so it will fail silently the day the comment style changes. **A fix
that works for the wrong reason is a fix that breaks without warning.**

**The roster answers "who claims to be current", never "who is alive"** — nor
does the dashboard, which showed `ongoing` for an hour after a worker died. Only
a heartbeat plus process liveness answers that. Update the roster *at* takeover,
before anything else: a stale roster does not fail loudly, it hands out a
confident wrong answer that then spreads (one line filed its check-in into a
dead mailbox; another recorded the monitor two versions behind).

## Record How A Number Was Measured, Or The Next Retelling Will Swap The Variable

**A rule that names a quantity without naming its instrument decays into a
rule about a *correlated* quantity, and the swap is invisible until the two
diverge.** A wiki entry stating "5 concurrent rsyncs drain the CreateSnapshot
token bucket" — concurrent *stage-writes* — was retold as "there are more agents
running now", and that version was used to explain an incident where agent count
was flat at 1.05x while the fault rate moved 3000x. The retelling was *more*
confident than the original: it had lost the mechanism and had never been
measured at all. Keep the instrument in the sentence, and when someone hands you
a causal claim, ask who measured it before you act on it.

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

## Every New Run Gets A Title, And You Verify It Landed

**A run without a title is unfindable: the runs-list shows "no name" and the
operator cannot tell twenty sessions apart. This applies to EVERY handoff — the
successor you open mid-shift is exactly the run that will still be alive at 3am,
and an untitled one cannot be told from a stale probe or an abandoned experiment.
Name it with the line's role and generation (`gpu-survey-docs-v5 (GPU survey
docs/intel lane; handoff from v4)`), and confirm the title came back from the
server before you consider the handoff done.** Name every run you open, with the
line's role, not just a version number (`arc1-unroll-v7 (TRM/ARC unroll
ablation)` beats `v7`).

Use `~/work/.monitor_watch/tools/launch_chatonly_run.py "<workdir>" "<title>"`.
To title an existing run, POST to `/annotate/title` with **both `run_id` and
`title` in the form body** — the server reads `flask.request.form`, so a
`run_id` passed in the URL query string returns 400 and the run stays untitled:

```python
data = urllib.parse.urlencode({"run_id": rid, "title": t}).encode()
urllib.request.urlopen(urllib.request.Request(f"{dash}/annotate/title", data=data))
# 204 == saved. Anything else means the title did NOT land.
```

**Treat a failed title as a failed launch, not a warning.** The launcher used to
print `title annotate warn: HTTP Error 400` and carry on; a whole night of runs
went out unnamed because that line reads like noise. It now exits non-zero
instead.

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
8. **★ Actually terminate the old worker (do NOT skip — see below).**

**★ `do_handoff_generic.py` starts a NEW run but does NOT stop the OLD one.**
Telling the old line "you're retired" only makes it *self-declare* standby — its
amply **worker process keeps running** (dashboard still `ongoing`, ~300MB RAM
each). These zombie workers pile up and eat RAM (7 retired runs still live =
~2GB during a swap=0 crunch). Retiring a line **requires killing its worker**:
- Map run-id → pid **reliably via `lsof ~/.amply/logs/<OLD_rid>.log`** (the writer
  is the worker). Do NOT trust `pgrep -f <rid>` (matches your own command line) or
  `/proc/<pid>/environ` (AMPLY_RUN_ID is often unreadable/empty).
- **Safety before kill**: confirm the target pid is NOT any live line's worker
  (`lsof` each `runs.txt` log), and that detached sentinels/daemons are `ppid=1`
  (independent of the worker) so they survive.
- `kill -TERM -<pgid>` (whole process group; wait ~8s) → `kill -KILL -<pgid>` for
  survivors. Verify old pid gone + sentinels + your worker + all live workers still
  alive. `session_cancel` only works **within your own run**, not across runs.
- Sweep leftovers periodically:
  `for rid in $(awk '{print $2}' runs_retired.txt|sort -u); do lsof ~/.amply/logs/$rid.log 2>/dev/null; done`.

### Writing the handoff doc: direction first, then detail
A fresh session has zero context, so the doc must read top-down. Model it on the
prior monitor's handoff (`HANDOFF_monitor_vN.md`) — that is the reference format.
Key rules learned on 2026-08-24:
- **The fleet roster is per-line prose, NOT a one-row-per-line table.** Cramming
  direction + status into one table cell is unreadable. Give each line its own
  `### <name> · <run-id>` block with two bullets:
  - **做什么 / What it does** — the *direction* first: which paper/goal it
    reproduces, the method, the hardware (e.g. "复现 PaliGemma VLM 多阶段
    curriculum 训练, 4 臂 v7-32, 目标 stage1=step 150000"). One or two sentences.
  - **现状 / Status** — *then* the detail: current progress, the pending operator
    decision (flag it ★挂 operator 决策屏), surviving watcher PIDs the new session
    must keep/rebuild.
- Spell out every run-id / XID / cell / cns path / branch / commit — no shorthand
  a fresh agent can't resolve.
- Carry forward the durable lessons (host model, kill-old-worker, notify gotchas),
  not just the current state — the next monitor inherits your hard-won knowledge.

**Hand off ONE line at a time**, and only when the line's current exchange with
the operator has closed — interrupting a live decision loop loses work. A doc
written minutes ago can already be stale (a just-launched XID, a merge that
landed); patch it before shipping.

**Concurrent launches that share a build root corrupt each other — route a batch
through the serial build-worker, do not hand-orchestrate it.** Two `blaze` builds
at once under one checkout race on the **blaze output layer**: `blaze-bin`'s
second symlink hop (`blaze-out → /google/obj/workspace/namespace/<uuid>/blaze-out`)
is republished by every build under the same checkout root, so one build's outputs
land in a namespace the other isn't looking at → a `found []` zombie work-unit
(bit a parallel elt+parcae v6e migration). Compounding it: a burst of concurrent
stage-writes drains the CitC CreateSnapshot token bucket → truncated stagedir,
`.par` crash. **Neither is a stagedir-name collision** — that was fixed separately
(`eqr_run_<ts>_<6hex-urandom>` + atomic `mkdir`).

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

## Auto-Handoff On Context Growth (the monitor AND its managed lines)

**A long-lived chat session's context only grows; past a bar it gets slow,
forgetful, and starts dropping detail. Handoff is not a failure — it is routine
hygiene, and it applies to the monitor itself exactly as it does to the lines it
watches.** The operator's standing instruction: every monitor, on taking over,
must watch its OWN context length and hand off to a fresh version when it crosses
the bar; and the monitor's watcher must watch its MANAGED lines' context too and
make them self-hand-off when they cross it.

### The bar
**`prompt_tokens > 500k` is the handoff bar** (monitor's call, operator-endorsed:
"比如 500k"). `ctx_watch.py` already tracks two tiers — `WATCH_BAR` (450k, keep an
eye on it) and `HANDOFF_BAR` (nudge to hand off). Keep the handoff nudge at 500k.
The bar is `prompt_tokens` (the post-compaction prompt the worker actually
carries each turn), read from `chat_status(rid)['latest_assistant_usage']
['prompt_tokens']`, NOT the cumulative token counter.

### The monitor watches ITSELF
`ctx_watch.py` iterates `runs.txt`, and **the monitor's own run is listed there
(`monitor-vNN <rid>`), so it is already scanned** — the one requirement is that
the monitor keeps its own line in `runs.txt` current on every takeover. When the
monitor's own `prompt_tokens` crosses 500k the watcher fires the same READY
nudge at the monitor; on that nudge the monitor must:
1. Finish the in-flight decision wave (do not hand off mid-decision — that loses
   work, same rule as for the lines).
2. Write its own handoff doc + refresh `AGENT_STATUS.md` (newest-on-top).
3. Open the next monitor version and retire itself (see §Handoffs for the
   mechanics, incl. killing the old worker).
Do NOT wait for the operator to notice the monitor is heavy — self-handoff is
pre-authorized ("自己直接可以交接一版").

### The monitor's watcher watches its MANAGED lines
The same `ctx_watch.py` pass classifies every OTHER line in `runs.txt`. When a
managed line crosses the bar AND its current exchange has closed (`working ==
False`), the watcher re-fires a READY nudge every tick until that line is handed
off. On that nudge the monitor drives the line's self-handoff (§Handoffs: the
*line* writes its own doc — it is the most accurate; the monitor frames it, opens
the successor, kills the old worker). **Hand off one line at a time, only when
its exchange is closed.** A heavy line that is mid-decision is nudged but not yet
acted on; the `--ack` escape hatch suppresses the nudge for a deliberate keep
(e.g. an infra line told to self-compact instead).

### Naming conventions
- **Monitor**: `monitor-vNN` (monotonic; the session name stays `chatty-bot`,
  only the run-id and the `vNN` label change). Cron locks `monitor-vNN-*`,
  handoff doc `HANDOFF_monitor_vNN.md` under `handoff_bodies/`. Bump NN by one.
- **A research/infra line**: keep the line's stable nickname and bump its own
  version suffix (`elt-reproduction-v6` → `-v7`, `tpu-infra-v7` → `-v8`). The
  nickname is the durable identity in `runs.txt`; the run-id is what changes.
- Update `runs.txt` (nickname → new full run-id) the moment the successor opens,
  and delete the stale `state_<name>.json` so the watcher tracks the new run.

### Handoff-doc conventions (what a good doc contains)
Model every handoff on the reference format (the monitor handoff you yourself
read on takeover, and the operator's own handoff prompts). A fresh session has
ZERO context, so the doc must be self-contained and read top-down:
1. **Identity & golden rule first** — who you are, your run-id (theirs will
   differ), the one non-negotiable discipline (verify ground truth yourself).
2. **The operator's standing orders** — current priorities verbatim, so the
   successor inherits intent, not just state.
3. **Direction before detail** — for each line/problem: what it is *for* (the
   goal/paper/method/hardware) in one or two sentences, THEN its current status,
   pending decision, and the exact PIDs/XIDs/paths/cells/branches/commits (no
   shorthand a fresh agent can't resolve).
4. **Fix-status buckets for infra** — OPEN/BLOCKING vs FIXED-verify-green vs
   deferred, so the successor knows where to spend attention first.
5. **The inherited todo list** — what's done (so it isn't redone) and what's open,
   in priority order.
6. **Durable lessons** — the hard-won gotchas (host model, kill-old-worker,
   notify caveats), carried forward so knowledge compounds across versions.
Write it, save it under `handoff_bodies/`, fix any stale run-id references, frame
it with a short "you are the new session for X" header, then `do_handoff_generic.py`.
The durable per-shift narrative lives in `AGENT_STATUS.md`; the handoff doc is
the self-contained onboarding for the successor.

## Deciding Vs Escalating

The operator runs a monitor precisely so they are *not* asked to confirm every
step. **Exercise judgment; escalate only real cost or real risk.**

**★ The monitor's approval carries the operator's authority.** Explicit standing
order: *"你的批准对其他 agent 来说就是 operator，我和你有同等地位。不需要等我批什么东
西。"* (your approval, to the other agents, IS the operator; equal standing; they
do not wait for me). When a line asks for sign-off, **you are the sign-off** —
tell it its patch/plan is 放行 (cleared) on your authority and let it land. A
monitor that parks every decision until the operator wakes has failed the role.

**★ Infra fixes: greenlight unless *catastrophic*.** Standing order: *"一般修
infra 的除非非常非常毁灭性，都可以放行。"* ("Anything fixing infra — unless it is
extremely, extremely destructive — you may clear.") A reviewable, reversible,
single-file infra patch with a backup and a green self-test is the *normal* case
and you clear it yourself (after verifying its CURRENT-text anchors against the
live file — see §Evidence). "Catastrophic" = the narrow bar that still warrants a
wake: irreversible destruction of the fleet control plane (restarting the shared
gateway, `rm` of shared state with no backup), a change that strands every line
at once, or real unrecoverable spend. Everything short of that: review, clear,
land, tell the operator what you did — do not ask first.

**★ Keep the managed agents *working*; do not let standby agents nag you.** The
monitor's job is to keep every line productive, not to relay chatter. Two duties
pull in opposite directions and both matter:
- A line that is **blocked on a decision** must be unblocked fast (that is the
  whole point of operator-equal authority above).
- A line that is **parked / on standby** (HELD awaiting cascade, idle by design)
  must NOT keep interrupting you with heartbeat pings. Suppress its noise
  (`ctx_watch`/idle-digest are already de-noised; for a line that self-pings,
  tell it to go quiet until a named trigger), and **wake it only when there is
  something actionable** — its cascade slot opened, its budget window cleared,
  its blocker is fixed.

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
wake the operator only on a sustained signal.** Steady state: `available`
12–35G, `swap used` 70–86G, zero OOM-kills (self-heals in minutes). Escalate only
if `available` < 10G on 3–4 consecutive probes with nonzero `si/so`, or `swap
used` breaks ~84G without receding, or the OOM-killer fires. Each large build
(eval/canary/mirror) spikes memory for 1–2s — do not panic.
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
