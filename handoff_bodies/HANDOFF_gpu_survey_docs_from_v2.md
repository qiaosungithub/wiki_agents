# HANDOFF — GPU-survey DOCS/INTEL line (v2 → successor)

You are the successor on the **GPU-survey DOCS / INTEL / REPORTS line** for
operator qiaos, taking over from gpu-survey-v2 (session chatty-bot, run
20260827-164854-2c1e76b8). A fleet monitor watches your health. This doc is
zero-context: every id/path/commit is spelled out. Read §1 first — it is the one
thing that prevents a real accident.

────────────────────────────────────────────────────────────────────────
## 1. ★BOUNDARY — YOU DO NOT LAUNCH GPU JOBS. That is gpu-survey-v3's.
────────────────────────────────────────────────────────────────────────
monitor-v42 ruled (and operator authorized) a hard split:

| thing | owner |
|---|---|
| GPU real-hardware job launch (h100/gb200/b200, incl. PROD re-fire) | **gpu-survey-v3** — run `20260828-012259-578e0f6c` |
| writing to `~/work/parcae-jax/torch_impl` and other GPU workdirs | **gpu-survey-v3** |
| **docs / intel固化 / reports / cap_policy report** | **YOU (this line)** |

**Do NOT `tpu enqueue` any GPU job.** v3 and you share the workspace
(`~/work/parcae-jax/torch_impl`) AND the single serial build-worker; if you both
launch you get duplicate jobs + a scrambled queue. v2 nearly caused this and
stopping to clarify is what prevented it. If you think a job needs launching,
**message v3**, don't do it yourself. (send tool in §7.)

Your lane is: keep `~/work/wiki_agents/gpu_on_borg.md` + `tpu_reference.md`
accurate, turn the other GPU lines' findings into durable rules, and write
operator-facing reports. That's it. When there's nothing to fix, **stand by** —
"a line that stops at the right time is not failing" (both monitors said this;
v2 proved a doc-only line can still contribute the most).

────────────────────────────────────────────────────────────────────────
## 2. THE THREE GPU BLOCKERS (state of the real-hardware campaign)
────────────────────────────────────────────────────────────────────────
The whole toolchain is PROVEN (enqueue routing, CUDA build, ARM/aarch64
cross-compile for GB200, budget-window catch, reaching RUNNING). What remains is
three walls, each an operator-level grant or a wait:

### 2a. GB200 = IMEX NVLink authorization wall  [operator action, already escalated]
- A GB200 job reaches RUNNING then crashes 100% at CUDA/NVLink init with:
  `PERMISSION_DENIED: MDB role qiaos is not allowed to send request to CA pool
   projects/mn-nvlink-imex-proxy/locations/<region>`.
- GB200 is NVL72 (cross-node NVLink) → needs an IMEX (Internode Memory EXchange)
  proxy, authenticated via MDB group membership (`prod-imex-ra-users`-style).
- ★**The judge is the runtime crash + the source mapping, NOT `aclcheck`.**
  In this workspace `aclcheck` fails on the environment's own LOAS restriction
  (can't reach the ACL-proxy / ganpati-read principal) → a DENIED that is about
  "can you QUERY the ACL", not "are you in the group". Do not cite it. The hard
  evidence is: (i) the runtime PERMISSION_DENIED above, (ii) the CA-pool→group
  mapping in `security/ca/ra/imex/service/config/startup.pi` (mirrored in
  `production/borg/pod/miba/private-ca-front-end/server.pi`), (iii) the IMEX
  sidecar starts iff `IsGpuWithNvlinkDomain()` is true, which keys on CARD TYPE
  (GB200/GB300/VR200), not node count — so even single-node `gb200-8` hits it.
- The grant must cover **BOTH staging and prod RA** (borglet defaults to STAGING).
- gpu-survey-v3 prepared the application (in its artifacts). This is an
  operator-level IAM action; monitor has escalated it. You do not chase it —
  you document the conclusion once the grant lands or is denied.

### 2b. B200 = the IMEX-free NVLink path  [HYPOTHESIS, v3 verifying]
- `b200` (card 87) is a DISTINCT card from `gb200` (card 89), single-node NVLink,
  so `IsGpuWithNvlinkDomain()` is false → no IMEX sidecar → no CA-pool grant
  needed. Source-confirmed. B200 PROD is free-pool (0.0 cr/chip-hr).
- ★**But "b200-8 actually completes device_count==8 + NCCL end-to-end" is NOT
  yet proven** — treat it as a hypothesis until a real job writes a success
  verdict to CNS. Source only rules out THIS wall, not others. v3 is running a
  B200 soak (`b200-8-soak`, its own standalone binary at `~/work/b200_soak/`,
  NOT parcae code) to get that proof + measure hold-time. Do NOT write
  "B200 works" as fact in the wiki until v3 reports a CNS verdict.

### 2c. H100 = preemption  [operator lever = PROD, already granted]
- 6/6 H100 BATCH smokes died "Preempted. Due to a higher-priority job taking the
  chips" (FailedWorkUnits=0 = eviction, not a crash). Even on the g9 floor,
  BATCH is evicted by higher-priority floor jobs.
- HOOK D ruling: **H100 train/sanity now go `--tier=PROD`** (operator authorized
  direct PROD). BATCH is eval-only. That lever belongs to v3 (it launches).

────────────────────────────────────────────────────────────────────────
## 3. THE CAP-POLICY REPORT — official conclusion (do NOT reopen)
────────────────────────────────────────────────────────────────────────
File: `/usr/local/google/home/qiaos/.amply/artifacts/20260827-164854-2c1e76b8/REPORT_cap_policy_obsolescence.md` (this run's artifact
dir = `/usr/local/google/home/qiaos/.amply/artifacts/20260827-164854-2c1e76b8/`).
Finding: several TPU families' fixed limit-order caps (`cap_policy.py` /
`_tpu_limit_price_for_arch`) sit BELOW market at price peaks (v5p ~8x, v7 ~4x,
v6e ~2x, v6p intermittently), so PROD jobs in those families get held
`Queued (GQM price over limit order)`.
★**Official conclusion (monitor-v42 adopted it; NOT re-escalating to operator):
leave the table unchanged and accept the waits.** The cap refusing to overpay at
a peak is exactly what a blast-radius bound should do. The one thing NOT to do is
the middle path: leave the table stale AND hand-bump individual jobs. This is
consistent with operator's directives "if blocked on price, wait — price will
come down" + "reduce credit usage".
- It is NOT a `budget_check.py` bug — that gate now prices at market correctly
  (infra-v11's fix; see §5). The stale knob is `cap_policy.py`. Fix location if
  ever changed: `cap_policy.py` + its LINT-synced shell twin
  `_tpu_limit_price_for_arch`, never `budget_check`.

────────────────────────────────────────────────────────────────────────
## 4. WIKI EDITS v2 SHIPPED (branch google-internal-migration) — and WHY
────────────────────────────────────────────────────────────────────────
All in `~/work/wiki_agents/`. Commits, newest first:
- `0c3b225` gpu_on_borg Rule 4: **analog is ALSO LOAS-blocked**
  (`owner=analog-rdl-engine`) → the Borg log wall can't be worked around by any
  read path → a GPU job MUST self-write evidence (device_count + NCCL) to CNS,
  flushed within the first minute so a preemption still leaves proof.
- `5511724` gpu_on_borg Rule 5: two multicard-torch traps — (i) take `fork` from
  STDLIB `multiprocessing`, NOT `torch.multiprocessing` (g3-patched to
  `g3lib.multiprocessing`, asserts on `get_context("fork")`); (ii) the TRAINING
  path (not just sanity) must self-fan-out RANK/WORLD_SIZE or WORLD_SIZE=1 →
  per-proc batch = full global batch → strict reader rejects → startup death.
- `685e82e` gpu_on_borg: **PLACEABLE is necessary-not-sufficient** — `tpu
  queue-status` showing PLACEABLE only means the availability RPC answered; it
  does NOT test budget / IMEX / preemption. Only a real job reaching RUNNING +
  writing its own verdict is proof. (v2 found this by using its OWN failed
  campaign as the counter-example: a GB200 job sat PLACEABLE for hours, then
  crashed on IMEX.)
- `e4b237c` gpu_on_borg: fixed the IMEX evidence basis — replaced
  "aclcheck DENIED = you're not in the group" (wrong — see §2a) with the runtime
  crash + source mapping + `IsGpuWithNvlinkDomain` mechanism + staging/prod.
- `084d8c3` gpu_on_borg + tpu_reference: added the GB200-IMEX / B200-IMEX-free
  section, Rule 6 PROD-not-BATCH + no-job-bump, and replaced the stale
  "caps far above market" claim in tpu_reference with the cap-vs-market reality.
- (earlier this run: Rule 7 budget gate, GB200-ARM section, per-cell capacity.)

────────────────────────────────────────────────────────────────────────
## 5. NOT YOUR LANE, but know it exists (so you don't duplicate / collide)
────────────────────────────────────────────────────────────────────────
- **budget_check.py GPU-pricing fix = infra-v11's** (run
  `20260828-010847-09d072c5`). It is UNCOMMITTED WIP in
  `~/work/wiki_agents/tools/budget_check.py` (a `.bak_infrav11_*` backup sits
  beside it). It adds GPU families to `get_default_cap` + a GPU market-parse.
  **Do NOT stage/commit/edit that file** — when you `git add` your docs, add them
  by explicit name, never `git add -A`. Other lines' dirty files seen in the
  tree this run: `tools/budget_check.py`, `projects/rnn_unroll_adding.md`.
- The three torch-port lines own the model/training code (do not edit
  torch_impl/ internals):
  - parcae-torch-port = `20260827-202427-69db25fc` (workdir `~/work/parcae-jax`)
  - codi-torch-port   = `20260827-203017-6f6f4471`
  - trm-torch-port    = `20260827-203122-f64d40b7` (workdir `~/work/trm-torch`)

────────────────────────────────────────────────────────────────────────
## 6. ★METHOD you inherit (not a fact — a discipline). Now a fleet rule.
────────────────────────────────────────────────────────────────────────
`~/work/wiki_agents/AGENTS.md` §Evidence Order (commit `1ac2d4a`) says:
> **To assert that X has permission / fits / will be received, perform X once —
> do not query a status that describes X.** A status query almost always measures
> the *adjacent* thing, and it fails in the most expensive direction: it looks
> like supporting evidence.
The GPU lane is TWO of that rule's five worked examples: **aclcheck DENIED tested
"can you read the ACL", not group membership**; **PLACEABLE tested "did the
availability RPC answer", not "will the job run".** When you document any GPU
claim, apply this: prefer the runtime/source evidence over a status probe, and
close the loop at the far end (a job reaching RUNNING and writing its own verdict
— not "it didn't crash yet"). "Silent success is more dangerous than a clean
failure" — a `rc=0` / green status can be measuring the wrong thing.

Corollary that bit v2 this run: don't reason from a job's SUBMIT TIMESTAMP vs a
fix's commit time to conclude "it has/lacks the fix" — confirm the job actually
runs the code the fix touches (v2 wrongly guessed a B200 soak would hit a
training-path bug; the soak is a standalone binary that imports none of it).

────────────────────────────────────────────────────────────────────────
## 7. OPERATING NOTES
────────────────────────────────────────────────────────────────────────
- **Response language = Chinese** (operator convention, per `~/work/AGENTS.md`).
- **Red lines**: no `set_limit_order` job-level price bumps; BATCH = eval only;
  never `xm launch` / `xmanager launch` directly (always `tpu enqueue` + the
  serial build-worker) — but remember §1: you don't launch at all.
- **Message another session**:
  `timeout 20 python3 ~/work/.monitor_watch/tools/send11.py <run_id> < msgfile`
  (listeners are often busy → "Connection refused"/"not listening"; retry later,
  don't spin). Known ids: monitor (see runs.txt for the current monitor-vNN),
  gpu-survey-v3 `20260828-012259-578e0f6c`, the three torch lines in §5.
- **notify yourself from a background watcher**: `~/.amply/bin/amply_notify
  <your_session_id> "msg"` — session-id is the FIRST positional arg (from your
  `[NEW SESSION]` marker); the run-id goes in `AMPLY_RUN_ID` env, NEVER as the
  first arg. `rc=0` means "delivered to SOME worker", not "to the right one" —
  confirm at the receiver (this is the §6 rule again). The release binary at
  `$AMPLY_NOTIFY` is ACL-blocked; use the `~/.amply/bin/` local build.
- **srcfs/home I/O is heavily contended** — avoid walking big dirs (`find`,
  `ls -lt ~/logs`); read `~/.tpu_local_queue.json` + `~/.tpu_jobs.json` (fast)
  for job state, `code_search` not `grep -r` on /google/src/head.
- **git commit under contention**: `timeout 90 git commit --no-verify`; stage
  ONLY your own files by name.
- **Maintaining Memory rules** (`~/work/wiki_agents/AGENTS.md`): write the rule
  not the incident; no dates/jobids/source-line-numbers; replace stale facts,
  don't append a diary; lead each section with its bold rule; prefer a table to
  five bullets. Apply these to every wiki edit.

────────────────────────────────────────────────────────────────────────
## 8. IMMEDIATE STATE AT HANDOFF
────────────────────────────────────────────────────────────────────────
- No GPU job owned by THIS line is running (this line doesn't launch). v3's B200
  soak was RUNNING and being watched by v3 for a CNS heartbeat last v2 heard.
- Your lane is clean: cap report finalized, all wiki edits committed. Nothing
  in-flight, nothing burning resources.
- First move: read §1 + §6, skim `gpu_on_borg.md` so you know what's documented,
  then STAND BY. Act when a GPU line reports a finding to fold into docs, when
  the IMEX grant resolves, when v3's B200 verdict lands (update the hypothesis in
  §2b to fact-or-refuted), or when the monitor/operator directs you. Do not
  invent work.
