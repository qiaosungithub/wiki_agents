# HANDOFF — maze128 EqR-jax line (v6, for a fresh successor session)

> Self-contained. Written 2026-08-28 by chatty-bot, run-id `20260827-153048-14ec38b5`
> (line "maze128", successor to v5 run `20260826-230024-d281300c`). Operator = qiaos, converses in **Chinese**.
> Fleet monitor at handoff = **v44, run-id `20260828-071601-4ce2a82d`** (rolled v40→v41→v42→v43→v44 during this shift).
> ★ The monitor rid ROLLS OFTEN (5 times tonight). Before EVERY message to the monitor, re-read the CURRENT
>   rid from `~/work/.monitor_watch/runs.txt` — the line marked `# THIS MONITOR` (grep that marker; do NOT take
>   the bottom/last line, other successor lines can sit below it — that mis-delivery happened this shift). `send11` returns
>   "SENT ..." even to a RETIRED run-id — delivery success ≠ reached the current monitor. Two lines (incl. me)
>   mis-sent to a dead v42 tonight; two sentinels went silent for two days the same way. Ask for a one-word ack.
> Successor: read top-to-bottom; you can act from this alone. Monitor's approval = operator's approval.
> ★ GOLDEN DISCIPLINE: verify ALL ground truth yourself — live file/queue/CNS/code. Never trust a diff,
>   a marker, a memory, a status-cache, or even THIS doc's stale bits. (This shift I opened by mis-parsing
>   the queue as "0 entries" using the wrong top-level key — the real key is `entries`, 115 rows. Always
>   confirm structure before trusting a count.)

---

## 1. WHO YOU ARE + DIRECTION FIRST

- You are the **maze128 EqR-jax line**: research + liveness/coordination/reporting. You WRITE code/config.
- **What you reproduce:** EqR-jax = JAX continuous-space reasoning (reproduces locuslab/EqR paper). This line
  trains **maze128** (`Maze-128x128-offline`, 128x128 offline maze; grid head `mask_diffusion`; RON;
  muon/sqrt/last2 optimizer variants). **6 arms resume from a step-60000 checkpoint → target step 150000.**
- **Hardware:** each arm targets **v7-32-equivalent** compute (v7 ≈ 4× v4). Iteration is **PROD tier**
  (operator emphatic: BATCH only for eval, NEVER for training).

- **★ HEADLINE METRIC = accuracy on EMA weights** (this shift's decision, commit `408b1f46`, monitor-endorsed).
  - This SUPERSEDES v5's "training-loss is sole headline / EMA disabled" — that was RETIRED because it
    contradicted 24/24 live configs + the paper's own code (locuslab/EqR `evaluate.py`+`pretrain.py`).
  - maze metric names = `solution_acc` / `walk_acc`. Report training loss ALONGSIDE (not as headline).
  - Zero-rerun reversible. Full rationale: `EMA_headline_DECISION_BRIEF.md` (my artifact dir).

---

## 2. ★★ THE LAUNCH RECIPE (this shift's most valuable output — do this EXACTLY)

Firing a resume arm = enqueue ONE clean entry, then let the dispatcher build it. The two bugs below made
prior attempts silently cold-start or become empty shells; this recipe avoids both.

**Enqueue with a SINGLE `--launch=` flag, comma-separated k=v pairs, `load_from` as a TOP-LEVEL key:**
```
--launch=config=<CFG>,load_from=<CKPT>,exp_name=<EXP>
```
- ★ `load_from` is a **top-level launch key**, NOT `config.load_from` (see BUG-1).
- ★ Use **ONE** `--launch=` flag. Multiple `--launch=` OVERWRITE each other (see BUG-2).
- ★ `<CKPT>` must end at **`.../checkpoints/step_60000`** with **NO trailing `/state`**.
  `ckpt_util.py:1754` `load_training_state` appends `/state` itself — adding it yourself double-appends → crash.
  (Monitor's first example had `/state`; I caught it; all 20 fleet load_from values omit `/state`.)

**VERIFY BEFORE FIRING (falsifiable dry-run, on a THROWAWAY queue copy — never the live one):**
```
route_check.py ... --dry_run   # argv must show  --load_from=/cns/.../step_60000
                               # NOT --config.load_from=  and NOT empty
```
**VERIFY AFTER IT BUILDS (config dump in the run's CNS log):**
- run dir = `/cns/oi-d/home/qiaos/eqr_data/logs/EqR-jax/xid_<XID>_*_<exp_name>`
- confirm `load_from` NON-EMPTY in the dumped config AND the log says resuming **"from step 60000"** NOT "step 0".

---

## 3. ★ THE TWO STACKED BUGS (both silent — why they hid for weeks)

| # | bug | mechanism | symptom |
|---|-----|-----------|---------|
| 1 | key named `config.load_from` | dispatcher (`route_check.py:_queue_argv`) passes queue keys VERBATIM → emits `--config.load_from=` which is not a real flag → ignored | **silent cold-start at step 0** despite queue "carrying" load_from |
| 2 | multiple `--launch=` flags | `queue_cli.py:63-66` `_LAUNCH = flags.DEFINE_list(...)` = comma-separated list; repeating the flag OVERWRITES, only the LAST k=v survives | **empty-shell entries** (only `exp_name` left) = the row95/98/99 mystery |
- Neither errors out. That is why they persisted across several monitors.
- ★ The "empty shell" mystery (3 entries with only `exp_name`: `817127`/row95, `6ec303`/row98, `b36772`/row99)
  is SOLVED — it is BUG-2 at enqueue time, not data loss / queue corruption / zombies.

---

## 4. ★ THREE DEATH-TYPES — TRIAGE TABLE (grep the XID, do NOT infer from time)

A job showing FAILED can die three ways. **Always HARD-grep the enforcer log by XID** — I reversed my own
misdiagnosis (pruner→enforcer) exactly by grepping `~/budget_enforcer_tpu.log` for the XID instead of guessing.

| death | signature | where to confirm | self-heal? |
|-------|-----------|------------------|-----------|
| **pruner-delete** | compile/eval churn, ckpt-dir gc | pruner logs | n/a |
| **preempt** | borg reschedule | borg / analog | usually yes |
| **enforcer-pause** | `budget_enforcer.py --arm` pauses MOST-EXPENSIVE PROD job when cost>income/10; log line "cost=… most-expensive" | `grep <XID> ~/budget_enforcer_tpu.log` | ★ NO — claims "re-queued as resume" but requeue does NOT materialize; only FAILED left, zero QUEUED |

- 3-layer death confirm: local state=FAILED reconciled + `~/.tpu_check_cache.txt` absent + borg "Object not found".
- Tonight both row63(xid284204045) & row90(xid284212382) died of **enforcer-pause** (paused 01:42Z / 02:20Z,
  "cost=1082 most-expensive").
- ★★ **enforcer's "re-queued as resume" DOES materialize a new entry — but it COLD-STARTS (loses progress).**
  (CORRECTED by infra-v11 + monitor-v44, 08:30Z; this SUPERSEDES v43's "16 pauses / 0 requeues / pure canceller"
  claim, which was WRONG — see the judging-predicate lesson below.) Real accounting: **16 pauses → 14 requeued
  (5 building / 9 HELD) → 2 true failures** (283741482, 284061100/ImportError). NOT a pure canceller; ~12.5% fail.
- ★★ **The real bug is WORSE than "no requeue": the requeued entry has `load_from=MISSING` → it runs from
  step 0.** The enforcer enqueues only `--launch=resume_xid=<xid>`, and `resume_xid` is used ONLY to find the
  stagedir (reuse the code snapshot) — it does NOT load a checkpoint. Result across the fleet: **14/14 requeue
  entries have load_from missing = all cold-start.** More insidious than a no-op: the log says success, the queue
  has an entry, the job runs — only the step count silently resets to 0. (Also explains why the 9 HELD have high
  attempts: a cold-start costs the same as the original, so it re-busts budget and bounces straight back to HELD.)
- ★★ **JUDGING PREDICATE (learn this, it bit two monitors):** to tell whether a paused XID `x` was requeued,
  check `[e for e in entries if (e.launch_kwargs or {}).get('resume_xid') == x]` — NOT `e.xid == x`. The requeued
  entry's `xid` is None (not yet submitted); the original XID lives in `launch_kwargs.resume_xid`. So "paused XID
  as a LIVE entry's current xid" is ALWAYS 0 by design — that predicate can't distinguish success from failure.
  (v43 escaped the STRING trap `grep <xid> queue.json` but fell into a STRUCTURAL trap: right idea "string≠
  structural", wrong field — the correct structural field is `resume_xid`, not `xid`.)
- ★ **My arms, handled (08:33Z):** using the correct predicate, row63(284204045)→stub `v6p-32-729676` and
  row90(284212382)→stub `v6p-32-1328e8`, both BUILD_REQUESTED, config/exp/load_from=None, budget pre-debited.
  row63's stub would have DOUBLE-SPENT against my real `v7-32-d7de1d` (both build-eligible). I `tpu dequeue`d
  both stubs (my own jobs, monitor-v44 §④ pre-authorized). Verified: 117→115 entries, delta exactly the 2 stubs,
  d7de1d survives, no entry's resume_xid points at my XIDs anymore. row90 to be rebuilt fresh (§2 recipe).
- ★★ **I VERIFIED both my arms lost ZERO progress (measured, not assumed):**
  - row63 (284204045): `attempts=0`, `load_from=None` (it was itself a silent COLD-START via BUG-1!), and **NO
    CNS run dir exists at all** (`/cns/oi-d/.../EqR-jax/` lists 284206203/284212382/284215169 but SKIPS 284204045)
    → it never launched a borg job, wrote nothing. Rebuild from step_60000 = zero loss.
  - row90 (284212382): CNS dir exists but `checkpoints/` is EMPTY and the rank logs show no training-step output
    (died 16 min after launch, before the first save point). Rebuild from step_60000 = zero loss.
  - Resume ckpts for the fresh rebuilds survive: row63←xid282123151, row90←xid282496242 (step_60000 each).

---

## 5. ★ STANDING ACTIONS (recurring, learned this shift)

1. **After an enforcer-pause, the arm needs MANUAL rebuild — the enforcer's auto-requeue is a trap, not a fix.**
   The enforcer DOES enqueue a resume stub (find it via `resume_xid`, see §4), but that stub has
   `config/exp/load_from = None` → it cold-starts from step 0 AND can double-spend against your own real entry.
   Correct action: (a) find the stub by `resume_xid == <paused_xid>`; (b) `tpu dequeue <stub_job_id>` it;
   (c) enqueue a FRESH clean entry via the §2 recipe with the right `load_from` (latest CNS ckpt, no `/state`).
   Note FAILED is a terminal black-hole (dispatcher only picks up `QUEUED`; never revives FAILED), so the
   original paused entry (now FAILED) also needs a fresh replacement, not a state flip.
2. **Fire ONE arm at a time**, and self-verify budget headroom AT THE FIRE-MOMENT (the green window moves
   second-to-second). `budget_check.py --query <type> PROD 0 ""`. Tonight v6p new_cost 750.4 fit under 793.5.
3. **Use `--metros` not `--cell`.** All my arms land **tul** (nk/nl), co-located with the `oi-d` data bucket
   (tul). metros=['tul'] locked (tul-first: cheap, co-located, zero risk). cbf is phase-2.
4. Prefer **compile-cache eval** to reduce pruner risk (deferred item).
5. ★ **NEVER run a whole-tree `find` on the CitC/srcfs root** (`/google/src/cloud/.../google3`). srcfs is a
   shared network FS; a full-tree traversal is heavy I/O that throttles the ENTIRE fleet's staging. This shift
   my 3 orphaned `find ... route_check.py` / `ckpt_util.py` (started to verify code, parent shells exited so
   nobody read the output — pure waste) ran ~1h and coincided with an 04:18Z srcfs backend throttle that
   failed the elt-50k-FID eval build (`srcfsd is dropping writes`). To find code:
   - path KNOWN → `sed -n 'A,Bp' <abs-path>` directly (no search).
   - path UNKNOWN → `code_search` (indexed, no FS walk) or `grep -rn` scoped to ONE subdir
     (e.g. `.../experimental/users/qiaos/tpu_utils/`). NEVER a full-tree find.
   - ★ General rule on a shared workstation: before ANY traversal across the whole CitC/NFS tree, ask
     "can I narrow this to one directory?" — the answer is almost always yes.
   - Recover your own orphans: `pgrep -afu qiaos 'find /google/src/cloud'`; 3-check (owner / ppid / no locks)
     then kill. Recovering your own orphans is the responsibility of whoever started them.
   - ★ This rule is HARD-EARNED: it was violated THREE times this shift — by me (my 3 orphans), and the 3rd
     offender was **the monitor itself** (monitor-v44, 07:24Z, two `find`s under ~/work each hung 811s), who
     re-committed it WHILE the FS was already wedging and likely helped push srcfs D-count past the 15 alarm
     threshold. If a rule this explicit gets broken by the person who wrote it, keep the rule LOUD, not polite.
6. ★ **After ANY enforcer-pause: go to CNS, find the LATEST checkpoint, resume from IT — not cold-start.**
   The paused job may have banked real progress before dying (monitor-v43's arc1-v7 example: xid284231573 was
   paused 06:42:53Z but had cleanly saved `step_114000` at 06:41:32Z, 81s earlier — cold-restarting would waste
   114k steps). ALWAYS measure: `fileutil ls .../xid_<XID>_*/checkpoints/`. (My row63/row90 happened to have
   nothing banked — but I only KNOW that because I checked; do not assume.) `load_from` value has NO `/state`.
7. ★ **Do NOT re-fire an enforcer-paused arm until headroom actually recovered** — it was killed BY the budget;
   refiring into a red budget = instantly re-paused + one wasted `attempts`. Criterion: enforcer log shows
   `cap − current-PROD-cost > this job's cost` for **3 consecutive samples**. ★★ The 3-sample streak MUST NOT
   span an income jump (monitor-v44): if income changes mid-streak, DISCARD the streak and recount — else you
   decide on a price that no longer exists. Income is wildly non-stationary this shift: measured range
   **14735 .. 1801770, median ~25811** (>100× spread), so a streak stitched across a jump is NOT evidence of a
   persistent state. Concrete this shift: income at low end ~25811 → cap 2581, PROD 1882, free ≈699 — d7de1d
   needs 1441, so it stayed budget-gated (benign QUEUED↔BUDGET_DEFERRED, self-recovering each round).
8. ★ **Use the ENFORCER's cost figure for the job, not budget_check's** — they disagree (one job showed
   145.3 / 605.4 / 1082 tonight). The enforcer is what kills jobs, so budget-headroom math must use its ledger.
9. ★★ **Judging "was a paused XID re-queued?": the entry's `launch_kwargs.resume_xid == <xid>` — NOT its `xid`
   field, and NOT `grep <xid> queue.json`.** Three-layer lesson, each refuted the prior:
   - `grep <xid> queue.json` — STRING trap: false-hits on other entries' `load_from`/`last_reason` text.
   - `e.xid == <xid>` on a LIVE entry — STRUCTURAL trap (this one bit v43 AND my earlier self): the requeued
     entry's `xid` is None until submitted, and the paused XID is stored in `launch_kwargs.resume_xid`. So this
     predicate is ALWAYS 0 by design — it cannot tell requeue-success from failure.
   - ★ CORRECT: `[e for e in entries if (e.get('launch_kwargs') or {}).get('resume_xid') == x]`. Then ALSO check
     that entry's `load_from` (it will be MISSING → cold-start; see §4) before letting it build.
   "string exists ≠ structural exists" was right; the trap was picking the wrong structural FIELD.
    - ★ REFINEMENT (monitor-v44 08:38Z): the `xid` field finds the PREDECESSOR, not the successor — querying the
      16 resume_xids by `e.xid==x` actually hits 4 entries, all already-FAILED original entries. So the predicate
      isn't even reliably 0: **a predicate that's always 0 is obviously broken; one that's occasionally non-zero
      but whose non-zero hits are all the WRONG object is INSIDIOUSLY broken.**
    - ★ "A zero with no denominator is not evidence": a self-check that returns all-zero / all-green must FIRST
      prove it read anything at all. (docs-v4 read the wrong key — real key is `entries` — got all-zeros that
      "looked like perfect support" for its no-exposure conclusion. I made the SAME wrong-key error opening the
      queue this shift: `items`/`queue` → 0 entries, real key `entries` → 115. Always confirm structure first.)
   - ★ THIRD instance of the same family (observer-in-scope): after you rebuild a watcher, do NOT confirm it's
     alive with `pgrep -f watch_xxx.sh` — that false-hits on YOUR OWN currently-running command line (arc1 got a
     pid back tonight that was its own grep; the real watcher was dead). Correct: (a) `ps -eo args | grep
     "[w]atch_..."` (bracket the first char to exclude self), and (b) check the watcher's LOG is advancing —
     **trust (b) over (a)**. Note: after `setsid`, args may be a RELATIVE path, so an absolute-path grep also
     misses it (nearly made arc1 start a second instance). Same disease as #9 and §5.5: the judging predicate's
     scope accidentally includes the observer itself. Now you've seen three — you'll recognize the fourth.
10. ★ **srcfs wedge survival (learned hard this shift, monitor-v44 confirmed & self-corrected on it):**
    - It is an **infinite HANG, not an error** — a plain check that only asks "did the command error?" waits
      forever instead of failing. Put a `timeout` on ANY op touching srcfs paths (`~/work/...`,
      `/google/src/cloud/...`, `~/.amply/logs/...`).
    - ★★ BUT `timeout` is only half: a process doing I/O on a wedged mount goes into **D-state
      (uninterruptible sleep)** where even SIGKILL is not delivered — `timeout`'s kill can't reap it until the
      mount recovers (my send11 hung 1064s despite a 60s timeout). So `timeout` bounds "how long I WAIT", not
      "how long the process LIVES". And it never tells you whether your message was delivered — **delivery
      confirmation must be a remote ACK, not a local rc=0.**
    - ★ Do NOT declare recovery from LOCAL daemon metrics. Local `srcfsd` health (D-count, RSS, `ls` mount
      succeeds) measures the local daemon; the real stall source is often **BACKEND throttle** (bt≥8/600s,
      "Regurgitator disconnected"). v44 announced "recovered" from local metrics at 07:39Z and was wrong — a
      backend re-throttle at 07:49Z hung everyone again until 07:55Z. Confirm recovery by a real op completing
      fast (e.g. the same read that hung now returns in <1s), not by a proxy metric.

---

## 6. CURRENT STATE — 6 ARMS (live queue `~/.tpu_local_queue.json`, top-level `{entries:[...],updated}`, key=`job_id`)

★ Fire order: one at a time, fresh clean entry each, self-verify headroom each. Recipe = §2.

- **row63** `v7-32-d7de1d` — **QUEUED (I fired this, the fresh v2).** config `maze128_muon_ron_lr2e-4_wd0.1`,
  load_from `/cns/oi-d/home/qiaos/eqr_data/logs/EqR-jax/xid_282123151_20260822_033541_eqr-jax/checkpoints/step_60000`,
  exp_name `maze128-row63-resume150k-v2`, PROD/tul/[v7,v6p].
  ⏳ **OPEN ITEM — config-dump resume verification NOT YET DONE** (budget-gated, see below). As of 07:40Z
  d7de1d was still `xid=None`, oscillating QUEUED↔BUDGET_DEFERRED (cost 1441 > free headroom ≈699; income at
  low end ~25811). This is BENIGN self-recovery (dispatcher re-tests headroom each round), NOT a failure — do
  NOT re-fire, do NOT raise price (red line). ★ SUCCESSOR MUST DO: when d7de1d finally gets an XID, read
  `/cns/oi-d/home/qiaos/eqr_data/logs/EqR-jax/xid_<XID>_*_maze128-row63-resume150k-v2/logs/rank_0_attempt1.log`
  and confirm the config dump shows `load_from` NON-EMPTY AND the log says resuming "from step 60000" NOT
  "step 0". Report that line to the monitor. (I could not do this before handoff because the budget gate never
  opened during my context window — v44 explicitly OK'd shipping this as a marked OPEN item rather than
  waiting until my context ran out.)
- **row90** `v7-32-c60398` — FAILED (enforcer, xid284212382). Rebuild fresh: config `maze128_sqrt_lr2e-4_wd0.05`,
  load_from from `xid_282496242` (sqrtSpike-lr2e-4_wd0.05) `/…/checkpoints/step_60000`.
- **row91** `v7-32-9e7d95` — HELD, xid=None. Rebuild fresh: config `maze128_sqrt_lr2e-4_wd0.1`,
  load_from from `xid_282494558` (sqrtSpike-lr2e-4_wd0.1) `/…/checkpoints/step_60000`.
- **row95** — TWO stale entries to clear: empty-shell HELD `v7-32-817127` + zombie SUBMITTED `v7-32-91c1e8`
  (xid283586849, 08-26). Rebuild fresh: config `maze128_last2_lr1e-4_wd0.05`. ★ load_from ckpt source = MUST
  DETERMINE (find this arm's own step_60000 producer; do NOT reuse shell/zombie).
- **row98** — empty-shell HELD `v7-32-6ec303` + FAILED `v7-32-e87a45` (xid283540130). Rebuild fresh:
  config `maze128_last2_lr2e-4_wd0.05`. load_from ckpt source = MUST DETERMINE.
- **row99** — empty-shell HELD `v7-32-b36772` + zombie SUBMITTED `v7-32-e2277b` (xid283551835). Rebuild fresh:
  config `maze128_last2_lr2e-4_wd0.1`. load_from ckpt source = MUST DETERMINE.
- ★ row95/98/99: do NOT revive the old shells/zombies — build FRESH entries with the §2 recipe.

---

## 7. ★ OPEN ITEMS (carried forward — successor picks these up)
- [ ] **d7de1d config-dump resume verification** (details in §6 row63 block). Budget gate never opened during
      my context window; v44 OK'd shipping it as a marked OPEN item. Do it the moment d7de1d gets an XID.
- [ ] **Watcher for d7de1d**: I left `bg5` polling the queue, waking me (session `chatty-bot`) only on the
      meaningful transition (XID assigned / FAILED / entry gone) — NOT on the benign QUEUED↔BUDGET_DEFERRED
      oscillation. A background job dies with its session; **successor must rebuild an equivalent watcher**
      (poll `~/.tpu_local_queue.json` for `v7-32-d7de1d`; notify via `~/.amply/bin/amply_notify <your_sid> ...`).
- [ ] **row90/row91 rebuild** (fresh entries, §2 recipe, step_60000 load_from per §6) once budget recovers.
- [ ] **row95/98/99 rebuild** (clear each one's empty-shell HELD + its 08-26 zombie SUBMITTED/FAILED twin;
      DETERMINE each arm's own step_60000 ckpt producer; build fresh, §2 recipe).
- [ ] **Snapshot the cbf/lpp `_MIRRORS` generalization** from live tmpfs `data_util.py` back to the
      maze128-ablation branch + add §5 standing actions to MEMORY.md (see §9).

---

## 8. DATA / CODE LOCATIONS
- Launch tree = `/tmp/eqr_prenormsingle_launch` (tmpfs, ephemeral, workdir for all arms).
  Build target `//experimental/qiaos/eqr_jax_final:main`, STAGE_WS_ROOT=`/google/src/cloud/qiaos/elt_jax/google3`.
- tpu CLI (shell fn): `timeout bash -c "cd /tmp/eqr_prenormsingle_launch && source ~/work/tpu_cmd/tpu_wrapper.sh >/dev/null 2>&1 && tpu <cmd>"`.
- Monitor comms: `echo "msg" | timeout 25 python3 ~/work/.monitor_watch/tools/send11.py <monitor-run-id>`.
  ★ ALWAYS resolve `<monitor-run-id>` fresh from `~/work/.monitor_watch/runs.txt` — do NOT hardcode it; the
  rid rolls several times per night. ★ ANCHOR on the `# THIS MONITOR` marker, do NOT grab the bottom line
  positionally (other successor lines can sit BELOW it; the predecessor mis-sent to a sentinel-owner exactly
  that way). Use: `grep -a "# THIS MONITOR" ~/work/.monitor_watch/runs.txt | grep -oE "20260[0-9]{3}-[0-9]{6}-[0-9a-f]{8}" | head -1`.
  Current at this handoff = v44 `20260828-071601-4ce2a82d`. `send11` reports SENT even to a dead/wrong run-id,
  so request an ack for anything important.
- Queue: `~/.tpu_local_queue.json`. budget_check: `python3 ~/work/wiki_agents/tools/budget_check.py --query <type> PROD 0 ""`.
- amply_notify (per AGENTS.md, local copy): `~/.amply/bin/amply_notify <your_session_id> "msg"`.
- Data bucket = `oi-d` (tul). Data locality: cbf/lpp `_MIRRORS` generalized in LIVE tmpfs
  `/tmp/eqr_prenormsingle_launch/dataset/data_util.py` (both `_MIRRORS`(EVAL) + `_OFFLINE_MIRRORS`(TRAIN):
  prefix key "yucbf"→is-d, added "yulpptr"→li-d). ★ NOT yet re-snapshotted to the maze128-ablation branch.

## 9. DURABLE MEMORY DOC
- `~/work/EqR-jax-maze128-mem/` = isolated git worktree, branch **maze128-ablation**,
  repo git@github.com:qiaosungithub/EqR-jax.git (EqR-jax is NOT in google3 — external GitHub).
  MEMORY.md at repo root, pushed to GitHub, latest commit **a86522c4**. Canonical-owner rule: each direction
  keeps its own MEMORY.md on its own branch. ★ TODO: add §5 standing actions + §2 recipe + §3/§4 to MEMORY.md.

## 10. RED LINES (operator hard rules)
- ★ NO job-level price raising / set_limit_order ("没卡价格高就等着,价格会降").
- BATCH only for eval; training always `--tier=PROD`.
- FAILED is terminal → dequeue + fresh entry, never expect self-heal.
- row95/98/99: build fresh, do NOT touch old shells/zombies.
- Fire one at a time; self-verify headroom at fire-moment; use `--metros` not `--cell`.
