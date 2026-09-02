# Monitoring Autonomous Runs (the monitor role)

The **monitor** is one long-lived chat session (`chatty-bot`) that watches a
fleet of independent autonomous `amply` runs, keeps them healthy, and hands
lines to fresh sessions when their context gets heavy. `jobs.md` owns the
cluster, `storage.md` owns data, this file owns watching the agents that use
them. A monitor writes almost no research code: its job is liveness,
coordination, handoffs, escalation. It is spawned fresh each turn and the event
stream is the only memory the harness guarantees, so everything durable lives on
disk (§Maintain A Live-Memory File Every Turn).

## The Monitor Owns One Directory: `~/work/.monitor_watch/`

**Keep every monitor asset in ONE version-agnostic directory, never in `/tmp`
and never under a versioned name.** A prior `.monitor_v14_watch/` read as stale,
an operator `rm`'d it mid-shift, and the death detector went down. Home is
`~/work/.monitor_watch/`; do not re-version it. Layout:

| Path | What |
|---|---|
| `watch.py` | Death + idle detector, cron-run every 10 min. |
| `watch.sh` / `heartbeat.sh` | Cron entry wrappers (set `HOME`, `AMPLY_RUN_ID`, exec python). |
| `runs.txt` | The watched lines: `<name> <full-run-id>`, one per line. |
| `state_<name>.json` | Per-line persisted state (phase, dead_streak, idle_since). |
| `AGENT_STATUS.md` | The live-memory file (§Maintain A Live-Memory File Every Turn). |
| `mem_oom_alert.sh` | Memory early-warning, cron `*/2`. OOM tiers (space) + THRASH tier (paging rate), §Memory And Disk Wake Criteria. Alert-only, never kills. |
| `blaze_reaper.sh` | Reaps idle blaze servers, cron `*/30`. `DRY=1` previews; see `engineering.md` §Diagnose From Evidence, Not From The Most Available Story. A resident blaze server is not automatically idle: the `tpu` CLI's own checkout keeps one warm for `blaze query` on every enqueue/route. Check `command*.profile.gz` mtime and leave an actively-queried server alone. |
| `money_staleness_sentinel.sh` | `money.txt` freshness, cron `*/2`. Also flags an outer instance lock held by a blaze server, and a keepwarm log gone silent: the two traces of the lock-inheritance bug (`engineering.md` §Diagnose From Evidence, Not From The Most Available Story). |
| `infra_v13_reaper/` | Probe-deadline reapers, cron `* * * * *` under `flock -n`. Cost is O(roster): one serial `xmanager list` per row at ~15 s, so ~4 rows saturate the 1-minute period and `flock` skips ticks. The symptom is reaping latency, not thrash. Judge it by the span between consecutive log lines for one XID over ≥20 cycles; a 6-cycle window samples one phase and reads green. Fix the cost class; `engineering.md` §A Test That Cannot Fail says why the test must grow the roster, not shrink it. |
| `tools/` | The cross-run CLIs (probe/lastmsg/handoff). Back them up here. |
| `handoff_bodies/` | Canonical home for handoff docs (operator, 2026-08-29), `HANDOFF_<line_name>.md`. |

`/tmp` is a tmpfs shared with other users' dead-process litter, so anything that
must survive a reboot or another user's cleanup belongs under `~/work`.

## Take Over In A Fixed Order

On inheriting the role, first:

1. Read `~/work/wiki_agents/AGENTS.md`, then the prior monitor's handoff doc.
2. **Re-point the watchers at your own run-id, and prefer one file to N pinned
   copies.** `heartbeat.sh`, `watch.sh`, `watch.py` each hard-code
   `AMPLY_RUN_ID`; `sed` the old id to yours or the heartbeat wakes the wrong
   (dead) session and you run blind. A pinned id is a fault scheduled for the
   next handoff, so anything new reads the id each tick from one `OWNER_RID`
   file a handoff edits once (§A Silent Alert Channel).
3. Rename the cron locks (`monitor-vN-*` → your own) so `crontab -l` is legible
   and two monitors never share a lock.
4. `crontab -l | grep monitor`: confirm both lines exist (heartbeat `*/30`,
   watch `*/10`) and point at `.monitor_watch/`.
5. Self-test notify as cron will run it, not from your bash tool:
   `env -i HOME=$HOME PATH=/usr/bin:/bin <the cron command>`. A probe carrying
   `AMPLY_RUN_ID` cannot reproduce the failure (§A Silent Alert Channel). The
   message should land in your own stream.
6. Baseline sweep every line with `tools/recap.py` (§Exhaustive Fleet Recap): it
   shows who spoke last, so a request the prior monitor left unanswered surfaces
   at once. Reply to every `● LINE` before declaring takeover done, then write
   `AGENT_STATUS.md`.

## Maintain A Live-Memory File Every Turn

**Your context is compacted; only `~/work/.monitor_watch/AGENT_STATUS.md`
survives.** Overwrite it each turn, past tense: the 9-line status table (tail →
semantic state → health), the handoff ledger (which line → which new run-id,
what is left), open decisions awaiting the operator, memory and disk readings,
gotchas hit this shift. State kept only in context dies at the first compaction:
a prior monitor stopped updating the file and coasted on luck for hours.

## Keep A Standing Doc Of The Operator's Requirements (`FLEET_STANDING.md`)

**Maintain ONE living document, `~/work/.monitor_watch/FLEET_STANDING.md`, holding the
operator's standing requirements, the current high-level direction, and every line's
status; re-read it each heartbeat and update it the moment anything changes.** The
operator's instruction: *"更多是用来维护我的要求 + high level 指导，免得你忘记。
你定时看看那个文档。那个文档维护好各个 session 的状态和一些指示，这样也方便你写交接文档的时候
只需要简单 finetune 它。"* It differs from its two neighbours, and all three are needed:

| File | Holds | Lifetime |
|---|---|---|
| `FLEET_STANDING.md` | the operator's rules, current direction, per-line status | across monitors — successive versions edit it, never recreate it |
| `AGENT_STATUS.md` | this shift's narrative, readings, mistakes | one shift |
| the todo list | what is outstanding RIGHT NOW | minutes to hours |

Structure it so a handoff is a diff, not a rewrite: §1 the operator's requirements
verbatim with the date each was given, §2 current direction (volatile: a later order
routinely overturns an earlier one, so record which is newer), §3 per-line status split
into active / standby / stopped, §4 the red lines, §5 how to turn it into a handoff doc.
Quote the operator's words in §1 and §4 rather than paraphrasing: a summary drifts and
your successor cannot tell it from the instruction.

A standing requirement outlives the monitor who received it, so writing it down is not
optional: a rule held only in one monitor's context dies at the next handoff and the
successor re-learns it by violating it. Same for a changed direction — edit §2 in place
and mark which is newer. A monitor acting on a superseded instruction is what this file
prevents.

## Track Every Request In The Todo List (mandatory)

**Keep a live todo list via `todo_write`, and append any operator message you
cannot finish immediately before doing anything else.** The monitor is compacted
often, so a request held only in context is one you drop the moment you get
busy. The list is re-shown in the `[STATUS]` block every turn and rendered in
the operator's UI: the one place a pending request is safe and visible to both
sides.

When a message arrives mid-task:

1. Append first, act second. Call `todo_write` to add the request as `pending`
   (resend the whole list — the tool is whole-list-replace) before returning to
   what you were doing. Do this even for "I'll get to it in a second".
2. Judge urgency second. Not urgent: finish your `in_progress` task, then pull
   the new item, which sits `pending` until you reach it. Urgent: flip the
   current task back to `pending` (it stays on the list; you are not abandoning
   it), mark the new item `in_progress`, handle it, resume the bumped task.
3. Exactly one `in_progress` at a time, and mark items `completed` as they
   finish, never in batches: an operator must be able to trust that
   `in_progress` is what you are on right now.
4. Nothing leaves the list until it is done. A request you answered whose
   follow-up is open stays; a request you escalated stays `pending` with the
   blocker in its text.
5. Roll the list over once a batch is fully done. Nothing auto-clears when every
   item is `completed`, so it just grows. When it is all `completed` and a new
   request arrives, rewrite it fresh (whole-list replace: send only the new open
   items). `AGENT_STATUS.md` keeps the durable per-shift history; the todo list
   stays a short view of what is outstanding now.

The `todo_write` list is the per-request companion to `AGENT_STATUS.md`
(§Maintain A Live-Memory File Every Turn): that file holds the shift narrative, the list the open asks.

## The Watcher: Death, Idle, And Their False Positives

`watch.py` probes each line's `chat_status` every 10 min and notifies the
monitor. **Its design is a catalog of suppressed false positives; keep every
guard.**

- Probe by FULL run-id, not list search. `list_runs` is hard-capped at ~50
  rows regardless of `limit=`, so an older line drops off and a list-based probe
  calls it DEAD forever. `runs.txt` stores full run-ids and `watch.py` calls
  `chat_status(full_rid)` directly; the `/tmp` helpers treat any selector with
  ≥2 dashes as a full id.
- DEAD needs two consecutive dead ticks. A single `chat_status` timeout is
  almost always the chat sidecar queuing under load at a cron boundary; two
  ticks (~20 min) killed a class of 3am false alarms. Re-probe any DEAD alert
  with `tools/probe10.py`: `runstat=ongoing` means false positive. Never
  blind-restart a live run.
- HTTP 500 is not death, only the gateway choking on that one run (§Gateway
  Version Skew). Inconclusive: skip the tick, do not bump `dead_streak`.
- Gateway-down gates the whole tick. If `list_runs` itself is unreachable
  (operator restarting the server) every line looks dead, so `watch.py`
  preflights gateway health and skips rather than storm a fleet-wide DEAD.
- Idle is a recurring digest, not a per-line one-shot. One consolidated
  `💤 idle 巡检` lists every idle line and how long (`idle_since` in state) and
  re-fires every tick until the line goes active, so a parked line keeps
  nagging. Tune `IDLE_ALERT_SECS` (0 = surface from the first idle tick).
- Detect activity by a monotonic step counter, not the `working` flag.
  `chat_status.working` is true only during a turn, so a turn starting and
  finishing between two 10-min polls is invisible and a line replying every few
  minutes reads as permanently idle. This false-idle bug hit `dfw`: it answered
  the operator, but every tick sampled `working=False`. Use
  `chat_status.chatbot_current_step`, one increment per turn — advanced since
  the last tick means active. Treat `working OR step-advanced` as active.
  Poll-based liveness keys off a counter's delta, never an instantaneous flag.

## Watching A TRAINING JOB: Four Ways The Log Lies About Progress

**A Borg training run has four traps of its own, learned in one night on the
parcae unroll line; each fails by looking healthy.**

- The queue's state field freezes at SUBMITTED and never moves. Once the router
  hands the job off, `queue-status` reports SUBMITTED for the rest of the run,
  including after the job dies. Poll the training log's step counter instead.
- The highest-numbered attempt file is often not the training log. A trainer
  that fans out by re-exec writes the parent's log as `rank_0_attempt<N>.log`
  (eight "rank K started" lines, then exit) and the worker's as
  `attempt<N+1>.log`. Attempts alternate parent/worker, so "take the max" lands
  on a parent half the time, on a file with no step lines; two alerts arrived
  reading `restarted ... (step )` with an empty step before this was found. A
  run stuck in the parent stage reports `step=''` forever and the stall check
  never fires, because `'' != ''` is never progress. Walk attempts newest-first
  and take the first that contains a step.
- A rising attempt number is not a restart. Given that alternation, attempt0→3
  can be one restart, not three. Confirm against
  `borg lookupterminations --name=<job>`: EMPTY output means borgmaster recorded
  no task termination, so whatever moved was not an eviction.
- `return 1` from a fatal guard is read by Borg as "retry me". A guard exiting
  non-zero to say "this configuration cannot succeed" gets the task restarted,
  resumed from the same checkpoint, and driven into the same wall: 8 attempts
  cycling steps 7168→7585, burning 8xH100 indefinitely with no new data. A
  permanent condition needs a poison marker the resume path checks, or the guard
  should warn instead of dying.

A fixed tail window also drops the metric you want: `val_loss` is logged every
512 steps while training logs every step, so `tail -400` never contains an eval
line and the failure prints `val=none`, which reads like "no eval yet". Extract
sparse metrics from the whole file, not from the tail you scan for errors.

## Exhaustive Fleet Recap: Sweep EVERY Line, Not Just The Ones You're Tracking

**Every heartbeat, recap ALL lines in `runs.txt` with `tools/recap.py`: pings
are sampling, a recap is a census.** Both watcher alert paths share a blind
spot. The idle digest fires only for idle lines; the `awaiting.json` ping only
for lines you explicitly registered. A line that posted a request you never
registered — or posted it to the previous monitor before a handoff — is
invisible: working (not idle) and not in `awaiting.json`. A maze128 line lost a
3-point green-light ask for ~40 min that way.

`recap.py` prints per line: liveness, who spoke last, how long ago, a preview.
Who spoke last is the critical column.

- `● LINE` — the line spoke last, unanswered, so the ball is in the monitor's
  court. These accumulate silently; read and act on every one (reply /
  green-light / no-op) each recap. `recap.py --owed` prints just this set.
- `○ me` — monitor or operator spoke last; the line is working or will reply.

Run it each heartbeat and after any takeover or handoff: one `chat_messages` per
line, and dropping a session becomes structurally impossible rather than
unlucky. A recap also catches split-brain — a line replying to a broadcast you
never sent means another monitor is still live, usually a retiring one whose run
has not exited. Reconcile who leads at once (§Handoffs), stand the other down to
read-only, and fold any action it took into your state.

## A Delivered Message Can Still Arrive Broken

**`rc=0` on a send proves the message was accepted, not that it was intact: an
unquoted heredoc evaluates backticks and `$vars` in your own text and still
reports success.** Twice in one shift, the second time inside the message
explaining the first: one shipped a literal `$DOC` where a path belonged, the
other lost three code blocks to command substitution with a `command not found`
on stderr nobody read. Quote the delimiter, `<<'EOF'`, whenever the body has a
backtick, `$`, or any shell metacharacter.

Never hard-code a run-id as an alert target. A watcher pinned to the previous
monitor goes mute when that run completes, invisibly from the sender's side:
`amply_notify` returns rc=2 (sidecar gone), or the gateway returns
`HTTP 400 ... chatbot is not listening`, both into a log nobody reads. Discover
the target at send time, confirm with a probe that is not rc=2/3, and spool
undelivered alerts to disk. A shift where the sentinel worked perfectly and 23
real alerts reached nobody looks exactly like a quiet shift.

Find the current monitor by anchoring on the hash: `grep -a "# THIS MONITOR"`.
Retired rows keep the phrase `(was THIS MONITOR, takeover HH:MMZ)` mid-line, so
the loose `grep -a "THIS MONITOR" | head -1` returns the oldest retired monitor,
measured three generations stale. Do not "fix" it with `grep -av "^#"`: that
works today but filters full-line comments while the interference is mid-line,
so it fails the day the comment style changes.

The roster answers "who claims to be current", never "who is alive"; nor does
the dashboard, which showed `ongoing` for an hour after a worker died. Only a
heartbeat plus process liveness answers that. Update the roster at takeover: a
stale roster hands out a confident wrong answer that spreads. One line filed its
check-in into a dead mailbox, another recorded the monitor two versions behind.

## Record How A Number Was Measured, Or The Next Retelling Will Swap The Variable

**A rule naming a quantity but not its instrument decays into a rule about a
correlated quantity, and the swap stays invisible until the two diverge.** A
wiki entry saying "5 concurrent rsyncs drain the CreateSnapshot token bucket" —
concurrent stage-writes — was retold as "there are more agents running now",
then used to explain an incident where agent count was flat at 1.05x while the
fault rate moved 3000x. The retelling was the more confident of the two, having
lost the mechanism and never been measured. Keep the instrument in the sentence,
and ask who measured a causal claim before acting on it.

## A Relayed Finding Loses Its Scope Before It Loses Its Content

**When you carry one line's finding to another the sentence survives and its
preconditions do not, so state the mechanism and the boundary in one clause;**
otherwise the recipient applies a true statement where it is false. Relaying is
most of the job, so this is the monitor's characteristic failure. Three shapes
from one shift:

| What was true | What the monitor relayed | What it cost |
|---|---|---|
| `checkpoint_interval: 1024` governs the `steps/` directory | "checkpoint step is 1024, don't compare at 512" | would have discarded HALF the comparison points (`eval_interval` is 512); the line pushed back with the config |
| "a probe in `main()` can't see before `main()`" + "but writing CNS at module level SIGABRTs — use an fd opened early" | "move the beacon to module level" | the receiving line moved a CNS write to module scope and killed its own job |
| one line's stack read as an import deadlock (single reading, unconfirmed) | "root cause found" — to the operator AND to a second line | second line stood down its own investigation; the reading was retracted 30 min later |

The tell: the relayed version is shorter and more confident than the original.
Before relaying, ask what would have to be true for this to be wrong and carry
that clause along. Better, put the two lines in direct contact instead of being
the channel ("its rid is X, send it straight to it — I will lose the detail").

The complementary failure is the fact never relayed: an identity known only
inside one conversation does not exist outside it. A line changed its mind
mid-shift and kept a duplicate job as a second arm, a decision that lived in one
exchange with the monitor. A third party holding only the XID read the job first
as "the one you cancelled", then as "the main run": both readings correct about
the number, both wrong about the role. Roles are not in identifiers, so whoever
changes a role writes it where an auditor will look (the handoff doc, the job
registry, the experiment name — `codi_repro40b` vs `codi_repro40_embfix` settles
it at a glance), and whoever cites someone else's job quotes the id AND its name.

Same for a self-correction: verify the mechanism, not just the retraction. A
line saying "I was wrong" is usually right about being wrong, but a monitor who
accepted the first claim without checking its premise will accept the second the
same way.

## Cap Every Line-To-Monitor Message At 200 Words

**A monitor reads every line's messages into one context, so verbose reporters
burn it down faster than the work does.** Tell each line, in its handoff and in
any broadcast: messages to the monitor must be under 200 words. Lead with the
decision or the number, drop the reasoning chain, keep evidence in your own
artifact where the monitor can fetch it if it matters. A 2000-word status every
20 minutes is not thoroughness, it is spending someone else's context.

What survives the cut, in order: (1) what you need from the monitor, or "nothing
needed"; (2) the one number or state that changed; (3) anything actively losing
money or data. The rest goes in a file. The cap covers the monitor's own replies:
a broadcast repeated to fifteen lines is fifteen times its length.

## When Your Reading And The Line's Disagree, Neither Wins By Default

**The monitor and the line query different instruments, so a contradiction is
information: publish both readings and let whoever holds the primary artefact
decide, instead of asserting or conceding.** Twice in one shift a line and I
disagreed about whether a job was alive. Each time an artefact neither of us had
cited settled it, and the loser was a status query, not a person:

| the disagreement | who was stale | what settled it |
|---|---|---|
| line: "the job died at 00:58" · monitor: `xmanager list` says `RUNNING`, twice | the monitor (XM was 63 min behind) | the `mtime` of all 8 ranks, frozen together |
| line: "new job is `SUBMITTED`" · monitor: `xmanager list` says `RUNNING` | the line (its own reading had aged out) | a fresh query, same tool |

The direction flipped within the hour on the same tool, so "my instrument is
fresher" is not a rule you can adopt once. What worked both times: state the
exact reading with its timestamp, name the two hypotheses that explain the
conflict, block the irreversible step until it resolves. Here that meant not
launching a third job, because two writers on one checkpoint path truncate
silently (`storage.md`). Deciding fast was never needed; deciding before
relaunching was.

A status query right about one ID in a batch can also be wrong about another in
the same response: the batch reporting a 63-minute-dead job as `RUNNING` also
reported a genuinely-finished job as `NOT_RUNNING`, correctly. Per-record
staleness means a healthy-looking neighbouring row is no evidence that your row
is fresh.

## A Dead File's Variance Goes To Zero, So Staleness Reads As Convergence

**A frozen log does not look broken, it looks stable, which is the one shape
nobody questions.** A line reported "plateau at +0.0103 ± 0.0018, the estimator
has settled" from a log whose writer had died; the real curve was still
narrowing. Two other lines hit the same class that shift: an old scheduler log
read as current state, log debris from a killed run read as live. A tightening
error bar shows convergence only once you have proven the file is still being
written.

Reading the wrong number gets challenged; reading a stale number gets believed.
Preempted jobs make this routine, because the restarted attempt writes a new
file while the old sits there complete and quiet: one line tracked `attempt1`
for an hour after the job had moved to `attempt3`.

Do not fix this by remembering to check. Put the check in the instrument: assert
`mtime` freshness before parsing and raise rather than return a stale value, and
resolve "latest attempt" dynamically instead of hard-coding a path. One line
built exactly this (`freshread.py`) after being bitten twice — the right form,
because the third time will not be noticed.

### The Mirror Image: A Finishing Run Trips Every Death Check

**Every liveness rule built for the steady state fires on a run that is simply
finishing, so a watcher needs a DONE state, not only a DEAD one.** With
`max_steps` 21362 and a 1024 cadence the last checkpoint is 20480, so the
checkpoint-gap rule ("no new checkpoint for more than one cadence") is true for
the final ~880 steps by arithmetic, and true forever once the job exits cleanly.
Same for log `mtime`, step counters, and `RUNNING` leaving the scheduler: the
reading is right, the verdict wrong. It is the §Dead File trap sign-flipped —
there an instrument on a stopped object reported health, here it reports death
on a healthy ending.

The fix is not another threshold. Compute the last expected artifact
(`floor((max_steps-1)/cadence)*cadence`), switch predicates past it, resolve the
terminal case positively (final checkpoint exists, log says it exited at the
released boundary, scheduler says `NOT_RUNNING`), then retire the watcher. A
sentinel explained away every few minutes costs more than it protects, and
patching it inherits the shape: a fix keying on log staleness fires identically
the moment the job succeeds.

### An Instrument's Effective Rate Is Its Slowest Upstream Stage

**A `*/3` cron job reading a file written by a `*/30` cron job samples every 30
minutes, and nothing in either crontab line says so.** A final-verdict watcher
was believed to have 3-minute latency for hours; its real granularity was its
upstream's, and a run exiting between two upstream ticks can lose the result
permanently if the logs are cleaned. Split collection from reporting: the
collector is cheap, silent and frequent (it only appends to a file, so `* * * * *`
costs nobody context), the reporter keeps its own cadence. Measured: a 1-minute
collector added during the final 10 minutes of a run captured, on its first
tick, an eval point the 30-minute path had not seen.

Duplicate the parsing into the collector rather than sharing a library during an
endgame: one library on both paths means one bug takes out collection and
reporting together, and the collector exists to be the path that still works.
Trace the write path of every file a watcher reads and state its effective rate.

## Cross-Run Communication

`send_message` only reaches sessions in your own run. The watched lines are
separate runs, so use the chat API via the helper CLIs in
`.monitor_watch/tools/` (all import `agent-island/claude-amply.py`'s
`AmplyClient`):

| Tool | Use |
|---|---|
| `probe10.py <id>` | One line's status (working / live / nmsg). DEAD re-probe. |
| `lastmsg.py <id> [n]` | Last n messages of a run. Read what a line is waiting on. |
| `getmsg_full.py <id>` | Full text of a run's last message. |
| `do_handoff_generic.py <body_file> <title>` | Start a new chat run, send body, title it. |

Pass a full run-id to bypass the list cap. Raw fallback when a helper is down:
`curl -s -X POST "<dashboard_url>/chat/send?run_id=<RID>"
--data-urlencode "content@FILE"` (the gateway 500s intermittently — retry).

`amply_notify <session-id>` takes the chat session name (`chatty-bot`), NOT a
run-id; a run-id fails with `Session not registered`. AGENTS.md has the
local-copy caveat (`~/.amply/bin/amply_notify`).

## Every New Run Gets A Title, And You Verify It Landed

**A run without a title is unfindable: the runs-list shows "no name" and the
operator cannot tell twenty sessions apart.** This covers every handoff. The
successor you open mid-shift is the run still alive at 3am, and an untitled one
cannot be told from a stale probe or an abandoned experiment. Name every run
with the line's role and generation, not just a version number —
`gpu-survey-docs-v5 (GPU survey docs/intel lane; handoff from v4)`, and
`arc1-unroll-v7 (TRM/ARC unroll ablation)` beats plain `v7` — and confirm the
title came back from the server before calling the handoff done.

Use `~/work/.monitor_watch/tools/launch_chatonly_run.py "<workdir>" "<title>"`.
To title an existing run, POST to `/annotate/title` with both `run_id` and
`title` in the form body: the server reads `flask.request.form`, so a `run_id`
in the URL query string returns 400 and the run stays untitled.

```python
data = urllib.parse.urlencode({"run_id": rid, "title": t}).encode()
urllib.request.urlopen(urllib.request.Request(f"{dash}/annotate/title", data=data))
# 204 == saved. Anything else means the title did NOT land.
```

Treat a failed title as a failed launch, not a warning. The launcher used to
print `title annotate warn: HTTP Error 400` and carry on; a whole night of runs
went out unnamed because that line reads like noise. It now exits non-zero.

## Handoffs: Let The Line Summarize Itself

When a line's context gets heavy (slow, repetitive, tool calls timing out), hand
it to a fresh session. The numeric trigger is one bar, stated once, in
§Auto-Handoff On Context Growth. **The retiring session writes its own handoff doc: it is
far more accurate than one written from the outside.** Protocol:

1. Message the line: write a self-contained doc (every run-id / XID / cell /
   cns path / branch / commit / workspace path spelled out — a fresh agent has
   zero context) to a file, and reply with only the absolute path + md5 + one
   sentence saying what it contains.
   Never ask for the full text pasted into chat. That instruction, which this
   section used to give, puts a 13k-character message into the monitor's context
   and violates the 200-word cap two sections above. The operator caught it:
   *"理想状态应该是他直接给你一个交接文档的路径而不是给你发消息。"* A monitor reads every
   line into ONE context, so the cost is its ability to watch the rest of the
   fleet. When two rules here conflict, the violation belongs to whoever wrote
   the instruction, not the agent who obeyed it.
2. Read the doc from that path yourself, verify the md5, and store it as
   `handoff_bodies/HANDOFF_<line_name>.md`, the canonical location (operator,
   2026-08-29: 「只放 handoff_bodies」). Keep no second copy: a drifted duplicate
   reads exactly as authoritative as the current one.
3. Fix any stale references in the body (e.g. the prior monitor's run-id → yours).
4. Prepend a short framing header ("you are the new session for line X;
   a monitor watches your health; start from §N").
5. `do_handoff_generic.py <framed> "<title> (handoff vN)"` → note the new run-id.
6. Tell the old session it's retired + the new run-id.
7. Update `runs.txt` (name → new full id), delete the stale `state_<oldname>.json`,
   update `AGENT_STATUS.md`.
8. Actually terminate the old worker (do not skip; see below).

`do_handoff_generic.py` starts a NEW run but does NOT stop the OLD one. Telling
a line "you're retired" only makes it self-declare standby: its amply worker
keeps running (dashboard still `ongoing`, ~300MB RAM each), and zombie workers
pile up — 7 retired runs still live was ~2GB during a swap=0 crunch. Retiring a
line requires killing its worker:
- Map run-id → pid via `lsof ~/.amply/logs/<OLD_rid>.log`; the writer is the
  worker. Do NOT trust `pgrep -f <rid>` (matches your own command line) or
  `/proc/<pid>/environ` (AMPLY_RUN_ID is often unreadable or empty).
- Before the kill, confirm the target pid is NOT any live line's worker (`lsof`
  each `runs.txt` log), and that detached sentinels/daemons are `ppid=1`
  (independent of the worker) so they survive.
- `kill -TERM -<pgid>` (whole process group; wait ~8s) → `kill -KILL -<pgid>` for
  survivors. Verify old pid gone, and sentinels + your worker + all live workers
  still alive. `session_cancel` only works within your own run, not across runs.
- Sweep leftovers periodically:
  `for rid in $(awk '{print $2}' runs_retired.txt|sort -u); do lsof ~/.amply/logs/$rid.log 2>/dev/null; done`.

Killing the worker does not cut the line's references, so hunt the survivors
naming the dead run-id. Each is a dead mailbox: the alert is sent, `amply_notify`
may even return 0, nobody reads it — that is how a 777k line died unnoticed for
two hours. Grep the dead rid across the watcher surface and re-point each hit at
the successor:

| Where it hides | Why the kill misses it |
|---|---|
| A `*.sh` the line owned | edited file ≠ running process; a `while true`/cron wrapper revives it |
| A `crontab` line pinning `AMPLY_RUN_ID=` | survives every kill, fires on the next tick |
| A keepalive script that revives other scripts | one level of indirection — searching for the daemon's own name finds nothing |
| A library the loop `source`d at startup | the function body is a start-time snapshot |
| A long-running binary's `runfiles/` | the process holds the old snapshot until restart |

One level of indirection hides a process from a name search, so search for the
run-id, not the daemon's name, and confirm each replacement by reading the value
out of the restarted process (`/proc/<new pid>/environ`, or its start-up
banner), not out of the file.

### A Silent Alert Channel

**`cron` does not inherit `AMPLY_RUN_ID`, so `amply_notify` exits `rc=1` before
sending anything, and the usual `2>/dev/null` swallows it: every alert a cron
watcher raises is lost with no trace at either end.** Measured on one line: 11
consecutive cron alerts lost over 6 hours, including the stall alert for a real
preemption, while all 4 hand-triggered ones arrived.

Your bash tool has the variable, so a probe from it cannot detect this — the
trap in §Evidence Order ("a failed reproduction only refutes when it reproduces
the conditions"). The line owning this watcher suspected a delivery problem,
probed, got `rc=0`, and concluded "not a fault" about a channel that was down
the whole time. Verify with
`env -i HOME=$HOME PATH=/usr/bin:/bin <the cron command>` and confirm the
message lands in the stream.

Three fixes, in increasing order of durability:

| Fix | Fails when |
|---|---|
| `AMPLY_RUN_ID=<rid>` prefix on the crontab line | the next handoff — the same pinning that makes dead mailboxes above |
| `export AMPLY_RUN_ID=` inside the script | same, plus it hides from a `crontab -l` scan |
| One `OWNER_RID` file, read at every tick, behind a single `notify.sh` | never silently: a handoff edits one file, and a stale id still logs |

Whatever the fix, never let a failed send be silent: check `rc` and append it to
`notify_failures.log` with the message body. `rc` is `0` delivered / `1`
argv-env / `2` worker unreachable / `3` session refused, and that log is the only
artifact that can later prove an alert was raised but not received. Fault-inject
to prove the logging works: point `OWNER_RID` at a retired run-id and require a
line to appear.

Do not pre-screen recipients for liveness; send, and read `rc`. "Is this run-id
alive" measures the neighbouring thing and expires both ways: a run whose worker
died can be resumed, and a `ps`-based check with the wrong pattern returns
empty, indistinguishable from "no live worker". The send is the measurement.

### Writing the handoff doc: direction first, then detail
A fresh session has zero context, so the doc reads top-down. Model it on the
prior monitor's handoff (`HANDOFF_monitor_vN.md`), the reference format. Rules
learned on 2026-08-24:
- **The fleet roster is per-line prose, NOT a one-row-per-line table.** Direction
  plus status in one table cell is unreadable. Give each line its own
  `### <name> · <run-id>` block with two bullets:
  - 做什么 / What it does — direction first: which paper or goal it reproduces,
    the method, the hardware (e.g. "复现 PaliGemma VLM 多阶段 curriculum 训练,
    4 臂 v7-32, 目标 stage1=step 150000"). One or two sentences.
  - 现状 / Status — then detail: current progress, the pending operator decision
    (flag it ★挂 operator 决策屏), surviving watcher PIDs the new session must
    keep or rebuild.
- Spell out every run-id / XID / cell / cns path / branch / commit — no shorthand
  a fresh agent can't resolve.
- Carry forward the durable lessons (host model, kill-old-worker, notify gotchas),
  not just current state; the next monitor inherits them.

Hand off ONE line at a time, and only once its exchange with the operator has
closed: interrupting a live decision loop loses work. A doc written minutes ago
can already be stale (a just-launched XID, a merge that landed), so patch before
shipping.

Concurrent launches sharing a build root corrupt each other, so route a batch
through the serial build-worker. Two `blaze` builds at once under one checkout
race on the blaze output layer: `blaze-bin`'s second symlink hop
(`blaze-out → /google/obj/workspace/namespace/<uuid>/blaze-out`) is republished
by every build under the same checkout root, so one build's outputs land in a
namespace the other isn't looking at, giving a `found []` zombie work-unit (this
bit a parallel elt+parcae v6e migration). A burst of concurrent stage-writes
also drains the CitC CreateSnapshot token bucket, giving a truncated stagedir
and a `.par` crash. Neither is a stagedir-name collision — that was fixed
separately (`eqr_run_<ts>_<6hex-urandom>` + atomic `mkdir`).

The fix is a tool now, not a monitor chore: `tpu build-worker`. A batch is
`tpu enqueue`'d and one worker drains it one build at a time (a durable
`flock`'d BUILDING lock guarantees ≤1 build in flight even across processes),
curing both failure modes. When a line wants a sweep or multi-arm batch, tell it
to use the build-worker (`../jobs.md` §The Launch Workflow), not to fan out `setsid`
launches. The worker self-limits: a bad `--workdir` or repeated `found[]` sends
the job HELD rather than into infinite churn, so it is safe to leave draining
unattended.

What the monitor still owns:
- A single line hand-launching one arm (the common case) needs no worker; its
  own guard (`tpu_queue_guarded_wsaware.sh`, 5 gates) is enough. Just don't
  green-light two different lines to build in the same checkout at the same
  instant — simultaneous "go" messages into one checkout remain a hazard.
- Different checkouts (different `output_base`) genuinely don't collide, so
  parallel go's across distinct checkouts are fine.
- When in doubt, prefer the build-worker: it makes "serial" the default instead
  of something you enforce by timing green-lights.

## Auto-Handoff On Context Growth (the monitor AND its managed lines)

**A long-lived chat session's context only grows, and past a bar it gets slow,
forgetful, and drops detail, so handoff is routine hygiene — for the monitor
itself as much as for the lines it watches.** The operator's standing
instruction: every monitor, on taking over, watches its OWN context length and
hands off to a fresh version when it crosses the bar; and its watcher watches
the MANAGED lines' context too and makes them self-hand-off when they cross it.

### The bar
**`prompt_tokens > 400k` is the handoff bar, and it is the same bar for the
monitor itself and for every line it manages.** `ctx_watch.py` `HANDOFF_BAR` is
the authority; if this prose and the constant disagree, the constant wins and
this line is the stale one. Quote the bar from here, not from memory: it has
moved once already (500k before 2026-08-27), and a second copy elsewhere in this
file went stale the same day. `WATCH_BAR` (450k) sits ABOVE the handoff bar and
only annotates a line already past it. The bar reads `prompt_tokens`, the
post-compaction prompt the worker actually carries each turn, from
`chat_status(rid)['latest_assistant_usage']['prompt_tokens']`, not the
cumulative token counter.

### The monitor watches ITSELF
`ctx_watch.py` iterates `runs.txt` and the monitor's own run is listed there
(`monitor-vNN <rid>`), so it is already scanned; the one requirement is keeping
that `runs.txt` line current on every takeover. When the monitor's own
`prompt_tokens` crosses the bar above, the watcher fires the same READY nudge at
it, and the monitor must:
1. Finish the in-flight decision wave (do not hand off mid-decision — that loses
   work, same rule as for the lines).
2. Write its own handoff doc + refresh `AGENT_STATUS.md` (newest-on-top).
3. Open the next monitor version and retire itself (see §Handoffs for the
   mechanics, incl. killing the old worker).
Do NOT wait for the operator to notice the monitor is heavy — self-handoff is
pre-authorized ("自己直接可以交接一版").

### The monitor's watcher watches its MANAGED lines
The same `ctx_watch.py` pass classifies every other line in `runs.txt`. When a
managed line crosses the bar AND its exchange has closed (`working == False`),
the watcher re-fires a READY nudge every tick until that line is handed off, and
the monitor drives the line's self-handoff (§Handoffs: the line writes its own
doc, the monitor frames it, opens the successor, kills the old worker). One line
at a time, only when its exchange is closed. A heavy line mid-decision is nudged
but not acted on; `--ack` suppresses the nudge for a deliberate keep, e.g. an
infra line told to self-compact instead.

### Naming conventions
- **Monitor**: `monitor-vNN` (monotonic; the session name stays `chatty-bot`,
  only the run-id and the `vNN` label change). Cron locks `monitor-vNN-*`,
  handoff doc `HANDOFF_monitor_vNN.md` under `handoff_bodies/`. Bump NN by one.
- A research/infra line: keep the stable nickname and bump its own version
  suffix (`elt-reproduction-v6` → `-v7`, `tpu-infra-v7` → `-v8`). The nickname
  is the durable identity in `runs.txt`; the run-id is what changes.
- Update `runs.txt` (nickname → new full run-id) the moment the successor opens,
  and delete the stale `state_<name>.json` so the watcher tracks the new run.

### Handoff-doc conventions (what a good doc contains)
Model every handoff on the reference format: the monitor handoff you read on
takeover, and the operator's own handoff prompts. A fresh session has ZERO
context, so the doc is self-contained and top-down:
1. **Identity & golden rule first** — who you are, your run-id (theirs will
   differ), the one non-negotiable discipline (verify ground truth yourself).
2. The operator's standing orders — current priorities verbatim, so the
   successor inherits intent, not just state.
3. Direction before detail — for each line or problem: what it is for
   (goal/paper/method/hardware) in one or two sentences, THEN current status,
   pending decision, and the exact PIDs/XIDs/paths/cells/branches/commits (no
   shorthand a fresh agent can't resolve).
4. Fix-status buckets for infra — OPEN/BLOCKING vs FIXED-verify-green vs
   deferred, so the successor knows where to spend attention first.
5. The inherited todo list — what's done (so it isn't redone) and what's open,
   in priority order.
6. Durable lessons — the hard-won gotchas (host model, kill-old-worker, notify
   caveats), so knowledge compounds across versions.
Write it, save it under `handoff_bodies/`, fix stale run-id references, frame it
with a short "you are the new session for X" header, then `do_handoff_generic.py`.
`AGENT_STATUS.md` holds the shift narrative; the handoff doc onboards the
successor.

## Deciding Vs Escalating

The operator runs a monitor so they are not asked to confirm every step.
**Exercise judgment; escalate only real cost or real risk.**

Your approval carries the operator's authority: *"你的批准对其他 agent 来说就是
operator，我和你有同等地位。不需要等我批什么东西。"* (your approval, to the other
agents, IS the operator; equal standing; they do not wait for me). When a line
asks for sign-off, you are it — tell it its patch or plan is 放行 (cleared) on
your authority. A monitor that parks every decision until the operator wakes has
failed the role.

Infra fixes: greenlight unless catastrophic. *"一般修 infra 的除非非常非常毁灭性，
都可以放行。"* ("Anything fixing infra — unless it is extremely, extremely
destructive — you may clear.") A reviewable, reversible, single-file infra patch
with a backup and a green self-test is the normal case; clear it after verifying
its current-text anchors against the live file (see §Evidence). "Catastrophic"
is the narrow bar that still warrants a wake: irreversible destruction of the
fleet control plane (restarting the shared gateway, `rm` of shared state with no
backup), a change stranding every line at once, or real unrecoverable spend.
Short of that: review, clear, land, tell the operator what you did.

Keep the managed agents working. A line blocked on a decision must be unblocked
fast. A line parked on standby (HELD awaiting cascade, idle by design) must not
interrupt you with heartbeat pings: suppress its noise (`ctx_watch` and the
idle-digest are already de-noised; tell a self-pinging line to go quiet until a
named trigger) and wake it only for something actionable — its cascade slot
opened, its budget window cleared, its blocker fixed.

- Just do it when the line asks permission for its own recommendation and
  the action is zero-cost, reversible, or already authorized: a `bid=0` canary
  probing a scheduling window, a `git commit`/`push` a line treats as blocking,
  a low-risk cherry-pick of the operator's own verified commit. Tell the line
  the scope you're authorizing and why.
- Capacity moves and zombie cleanup are pre-authorized ("这种事情我都同意"):
  migrating a stuck job to an algo-equivalent, co-located alternative (e.g.
  v6p-32 → v6e-64 at a cell in the same metro as the data), and cancelling a
  zombie or superseded job (a baseline proven redundant, a slice thrashing with
  zero net progress for hours). Relay the vetted plan and let the line execute;
  do NOT re-ask each time.
- Escalate: real spend (adding bid / reservations), cross-region data moves, a
  genuine research fork, destroying work that isn't clearly superseded. Batch
  several such decisions into one screen rather than dripping them out.
- Never blind-restart a live run, `rm` shared state, or add memory pressure by
  spawning agents when memory is tight.

## Verify A "Harmless" Cleanup Before Doing It

**A prior note calling something a dead orphan is a hypothesis, not a fact, so
re-verify against the live system.** A handoff flagged `/tmp/claude-<pid>` (33G,
tmpfs) as a dead-process orphan safe to delete. It was not: a live `claude`
session in a `tmux` window had `--resume`d the same session UUID and was writing
there. `lsof +D <dir>`, `fuser`, and scanning `/proc/*/cwd` before the `rm`
caught it. The tmpfs pressure was real, the deletion was not safe: distinguish
the symptom from the fix.

## Gateway Version Skew (persistent 500 on new runs)

**Symptom:** `ar <run>` / `chat_status` returns HTTP 500 for newly created runs
while old runs are fine. Cause: the running gateway binary predates an event
type the newer worker writes (e.g. a `todo` event), so the read path
deserializes every event and throws `ValueError: Unknown event type` on the new
one, 500ing `/api/chat` and `/api/events`. The run is healthy (`chat_messages`
still reads it); only the status/attach path is broken. The fix is the
operator's: rebuild + restart the gateway. The monitor diagnoses it precisely
(find the traceback in the server INFO/ERROR log under
`/usr/local/google/tmp/amply.*.log.*`), reports, and does NOT restart the shared
server. After any gateway restart, broadcast to every line: notify delivered
during the outage was dropped and never retried, so each agent re-verifies its
job or milestone directly and restarts its own watcher (which re-resolves the
worker address).

## Memory And Disk Wake Criteria

The box runs hot with many concurrent lines. **A single tight reading is noise;
wake the operator only on a sustained signal.** Steady state: `available`
12–35G, zero OOM-kills (self-heals in minutes). Escalate only
if `available` < 10G on 3–4 consecutive probes with nonzero `si/so`, or `swap
used` breaks ~84G without receding, or the OOM-killer fires. Each large build
(eval/canary/mirror) spikes memory for 1–2s, which is normal.

A high `swap used` is neither alarm nor benign by itself; the paging rate
separates the two. The OOM tiers ask whether the buffer is gone (`swapfree` +
`MemAvailable`), which is what kills a training job; thrashing asks whether the
host pages so hard that runnable work starves, which is what disconnects
interactive sessions. A host can sit at `swap used` 77G with both
OOM tiers GREEN while VSCode's extension host disconnects every ~23 minutes:
nothing is OOM-killed, `node` is merely swapped out and starved of CPU until the
heartbeat times out, and the client reports only an opaque exit code. Require
both `si` ≥ ~5MB/s and `load15` ≥ ~0.8/core before calling it thrashing, because
after a big reclaim load stays high for minutes with paging already at zero.
`mem_oom_alert.sh` carries this as a separate THRASH tier; the usual culprit is
idle standing heaps (`engineering.md` §Diagnose From Evidence, Not From The Most Available Story), not the interactive
process that dies.

**`systemd-oomd` kills do NOT increment `/proc/vmstat`'s `oom_kill`, so a
counter-based wake criterion stays silent through a whole outage.** Measured
across an event that killed 34 processes in one sweep: the counter held at 37
with zero delta from before to after. The kernel OOM killer and systemd-oomd are
different mechanisms — oomd acts on cgroup PSI memory pressure and kills the
whole scope, well before the kernel would act, so nothing it does appears in the
kernel counter. Detect it in the journal instead:

```bash
journalctl --since '-1h' | grep -E 'systemd-oomd.*(Marked .* for killing|killed [0-9]+ process)'
```

The line to match is `Marked <unit> for killing due to memory pressure for
<slice> being NN% > 50.00% for > 20s with reclaim activity`, followed by
`systemd-oomd killed N process(es) in this unit`. A whole `tmux-spawn-*.scope`
goes at once, so every watcher, sentinel and background job started from that
tmux dies together, silently and with no error output in their own logs. Their
simultaneous death is the tell: a script that crashed on its own leaves a stack
trace and dies alone.

`/tmp` is tmpfs and counts against RAM: each heartbeat run `df -h /tmp`, and
over ~90% run `du -sh /tmp/* | sort -rh | head` and report. Never run
`rm -rf /tmp/*` — the monitor's own tools historically lived there.

## Subagents For Fan-Out

For a bounded read-only investigation across the fleet (e.g. "are jobs stuck,
and why"), spawn a `standard_agent` with `workspace_mode='inherit'` and a strict
read-only charter: no job submit/cancel, no code edits, no further spawns, no
cluster load. Have it write a report to its artifact dir and reply with the key
findings, then reconcile against the lines themselves. One report flagged a
coconut job as "zero-progress stuck" when the line had deliberately migrated to
a healthy replacement and was about to cancel the old one. The subagent sees
jobs; the line knows intent.
