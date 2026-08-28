# parcae-torch-port — handoff (session 2 → 3), 2026-08-28 ~15:00Z

Predecessor session: `20260828-113635-ffefb3d0` ("parcae-torch-port v2").

> **Read the evidence tags.** [RAN] = I executed it and read the output.
> [CODE] = I read the source and inferred. [TOLD] = relayed, unverified by me.
> The single most expensive failure mode across this fleet tonight was a tag
> being stripped in transit, so please keep them attached when you re-transmit.

---

## 1. WHERE THIS ACTUALLY STANDS

Acceptance is three stages. **We are stuck in the middle of stage 2.**

| Stage | State |
|---|---|
| 1. Semantic alignment (local, vs JAX) | **DONE** — 7 components pinned numerically, by the *previous* session |
| 2. **Runs on a GPU** | ❌ **NEVER SUCCEEDED.** The code has still never executed with `device_count > 0` |
| 3. Reproduces the published number | ⬜ not started; target below |

**[RAN] The hard physical evidence: `out_dir` does not exist on CNS.**
```
fileutil ls /cns/is-d/home/qiaos/lyy_parcae_runs/parcae-140m-torch
  -> generic::not_found
```
⇒ This line has never produced a single checkpoint or a single line of training
log. Do not let any green-looking status persuade you otherwise; **that path
appearing is the first real milestone.**

---

## 2. LIVE STATE (verify before trusting — this is a snapshot)

**[RAN] as of ~15:00Z:**
```
job_id  h100-8-a0f015   state=QUEUED  attempts=1  xid=None  cell=None
        allowed_metros=['cbf']  allowed_archs=['h100']  tier=PROD
        launch_kwargs = {tpu_type:h100-8, group:9, tier:PROD,
                         exp_name:parcae-140m-torch,
                         config:remote_run_config,
                         bucket:/cns/is-d/home/qiaos/lyy_parcae_runs}
```
Re-check with (top-level key is `entries`, **not** `jobs`):
```bash
python3 -c "import json,os;d=json.load(open(os.path.expanduser('~/.tpu_local_queue.json')));
[print(e) for e in d['entries'] if e.get('job_id')=='h100-8-a0f015']"
```

### Two watchers are running, reparented to init (`ppid=1`), they SURVIVE the session
| what | pid | period | role |
|---|---|---|---|
| `watch_v2.sh` | 1222446 | 900 s | reports queue row + XID status |
| `persist_config_key.sh` (runs as `/tmp/parcae_persist.sh`) | 1370666 | 20 s | **maintains the two launch_kwargs keys** |

🔴 **KEEP THE PERSIST SENTINEL RUNNING.** [RAN] It has already restored the keys
**5 times** — the queue has a concurrent writer that replaces your whole row with
a stale snapshot, so a one-shot write does not stick. Judge both watchers alive
by **the heartbeat ADVANCING**, never by how fresh it is (a dying process writes
one last heartbeat):
```bash
A=$(cat ~/work/.parcae_torch_watch/persist_heartbeat.txt); sleep 22
B=$(cat ~/work/.parcae_torch_watch/persist_heartbeat.txt); echo $((B-A))   # >0 = alive
```
To restart either one, use `~/work/.parcae_torch_watch/restart_sentinel.sh` —
it encodes the ordering that matters (**start the new one first**, confirm its
heartbeat advances, only then kill the old one, and wait for `/proc/<pid>` to
actually disappear rather than `sleep 1`). Doing it the other way round opens a
protection gap exactly one polling period long.

---

## 3. WHAT I FIXED TODAY (all three would have wasted a launch)

| # | Defect | Why it mattered | Tag |
|---|---|---|---|
| 1 | `launch_kwargs` had **no `config`** | The launcher injects its own default `remote_run`, and `configs/remote_run.yml` **does not exist** in this repo ⇒ the job dies in config loading. Note the launcher *builds the path for you* (`xm_launcher.py:1307/1309`) — pass the bare name `remote_run_config`, never a path | [RAN] |
| 2 | `bucket` was unset | The default is `/cns/yutulpz-d/...` = **tul metro**, while our data, cell and out_dir are all `is-d`. It feeds `CHECKPOINT_BUCKET`, which decides where the sanity verdict and the log mirror land ⇒ **the job can run fine and write its only evidence somewhere you never look.** codi-torch is *already* a victim of this: its logs are in `/cns/yutulpz-d/home/qiaos/eqr_data/logs/codi-torch/` | [RAN] |
| 3 | Previous launch used a ghost-write staging root | XID 284355764 was built from a stagedir with **0 files** (I counted them) ⇒ `FailedWorkUnits 1/1`. The shared build worker moved to a healthy root at 12:36Z, so the re-queue is a retry **under a changed variable**, not a blind one | [RAN] |

---

## 4. NEXT STEPS, IN ORDER

1. **Wait for dispatch.** Do not requeue, do not dequeue (deletions get rolled
   back by the same writer), do not hardcode a `--cell` — `allowed_metros=['cbf']`
   is enforced inside the router (`route_lib.py:455`, pure Python) and hardcoding
   a cell would bypass the oversold/cooldown/price filters. [RAN]
2. **When an XID appears, verify in three layers.** An XID only proves *launch*:
   ```
   L1  xid exists                          -> launched, nothing more
   L2  xmanager.par list --experiment_id=<XID> --columns=ID,Status,FailedWorkUnits
         1/1                = real failure (a work unit ran and died)
         0/1 + RUNNING      = healthy
         0/1 + NOT_RUNNING  = zombie (no work unit was ever built)
         no row at all      = aborted and purged
   L3  the job's OWN output on CNS  <- the only layer that answers "is it working"
   ```
   `~/work/.parcae_torch_watch/verify_gpu_job.sh <XID>` runs 5 checks and is
   negative-controlled both ways. **Never use `list_artifacts`** — it reports
   "nothing found" for healthy jobs.
3. **Run `--sanity_only` first** if you get the chance: it writes its own verdict
   JSON to CNS and is the cheapest possible proof that 8 GPUs compute correctly.
   ⚠️ It has **never once produced a passing verdict on a GPU.** A deadlock that
   explained the previous evidence-free exit was fixed, but nobody has re-run it.
4. **Then the actual comparison** (script NOT written yet — this is the main
   piece of work left):
   - target: **val loss 2.9338 / val PPL 18.798** on `strict-4d1138c/validation`
   - JAX baseline XID **283958790** (`parcae-140m-nsgram-v4-reprotest`), curve at
     **[RAN]** `/cns/is-d/home/qiaos/lyy_parcae_runs/logs/parcae-jax/xid_283958790_20260827_072822_parcae-140m-nsgram-v4-reprotest`
     (found via `~/.tpu_jobs.json` → `bucket_cp_path`; it is *not* under
     `eqr_data/logs/parcae-jax`, which is where I first looked and failed)
   - `eval_interval` is **512** in `remote_run_config.yml`, so the first eval
     boundary is step 512 — compare there, do not wait for all 21362 steps
   - align to the **JAX row, not the paper row** (paper says 2.948/19.06; that
     gap is a data-layout difference the JAX line never closed)

---

## 5. STILL OPEN / NEVER VERIFIED

- **Nothing has ever run on a GPU.** Everything below stage 1 is unobserved.
- **All numerical parities are CPU/float32.** bf16, NCCL and fused attention have
  never executed. Bug #7 from the previous session (recurrent state being rounded
  to bf16) is precisely the class that only bites in bf16, at depth, over a long
  run — after the first GPU run, if `val/D8` and `val/D1` are implausibly close,
  suspect precision rather than the model.
- **8 concurrent strict readers against CNS** is untested (ranks 0/1/7 were read
  in one process).
- **No end-to-end curve comparison has ever been done.** The parts agree; the
  assembled run has never been compared to anything.

---

## 6. ENVIRONMENT TRAPS THAT COST ME REAL TIME TODAY

- **The queue has a concurrent writer.** `merge_and_save_touched` folds a stale
  whole-queue snapshot back over the live rows, so **field edits get reverted and
  deletions get resurrected**. [RAN] I measured 5 reversions in ~27 min, and they
  arrive in **bursts next to dispatch activity**, not uniformly. ⇒ Maintain state
  with a sentinel; never treat a successful read-back as proof it will stay.
- **`BUILDING` does not mean anyone is building.** It records that someone once
  *claimed* the row. [RAN] I found a claim 138 minutes old whose worker pid was
  long dead. Check `/proc/<worker_id pid>`; reclaim is lazy (only runs when the
  next build is claimed).
- **`submitted_at` can be hours old.** A state flipping to SUBMITTED may be
  bookkeeping catching up with an old XID, not a fresh launch. [RAN] I nearly
  reported "my job died 60 seconds after launch" for a 2.5-hour-old record.
- **Verify detach across a command boundary.** [RAN] `setsid` reparents to init
  only when the parent shell exits, so checking `ppid` *inside the same command*
  always shows a non-1 value and looks like failure.
- **A never-invalidated cache becomes a gravestone.** [RAN] The watcher kept
  reporting a dead XID's `1/1` after the row had been re-queued. It now
  reconciles its cached xid against the queue every loop.
- Local test checkout (has the parity drivers, none of them packaged for Borg):
  `/google/src/cloud/qiaos/clip_probe/google3/experimental/qiaos/parcae_torch_smoke_20260827_173917`
  ⚠️ Building there with `--config=cuda` is safe for other lines: each CitC
  workspace has its own `blaze-bin` (different output_base). [RAN]

## 7. RED LINES (carry verbatim)

- **NEVER** `xm launch` / `xmanager launch`. Only `tpu enqueue`.
- **Training is always `--tier=PROD`.** BATCH is eval-only and preemptible.
- **Never dequeue anything** — deletions are structurally non-convergent under
  the concurrent writer. Use HELD if you need to park a row.
- No job-level price raising (`set_limit_order`). If there is no capacity, wait.
- Do not modify the shared `~/work/tpu_cmd/tpu_wrapper.sh` or `xm_launcher.py`.
- Do not cancel or touch another line's jobs; one serial builder, do not fight it.
- Commit torch work to the `torch` branch; protect the dirty worktrees
  (`~/work/parcae-jax-nsfix` belongs to the JAX line).

---

## 8. WHAT HAPPENED AFTER 15:00Z (two launches, two different failures, neither of them our code)

**[RAN] Net result of the day: the port has still never executed.** Two cars went
out; both died before our code ran. That matters for how you read everything
above — "stage 2 not done" is not a guess, it is now twice-measured.

### Car 1 — XID 284355764, `FailedWorkUnits 1/1`
Built from a stagedir on the ghost-write root with **0 files** (I counted them
with `ls -A`). The work unit was created and died immediately: there was no code
in the package. **[RAN]**

### Car 2 — XID 284387576, `NOT_RUNNING 0/1` (zombie), and this one is the instructive one
`RUNNING` for 34 minutes, then terminal with **zero output in all three candidate
paths** (out_dir, the launcher's own `bucket_cp_path`, and the default tul bucket
— I grepped the default bucket for this XID specifically and got 0 hits, so it
was *not* a misplaced-output case). **[RAN]**

Then the stagedir told the real story. Its `config.sh` said:
```
PROJECT_NAME = "elt-jax-dit"
TARGET_LABEL = "//third_party/py/simple_diffusion/projects/latents:main_eqr"
find <stagedir> -name main.py  ->  0 hits
```
⇒ **[RAN] The car launched from our queue row was packaging and running ANOTHER
LINE'S CODE.** Every structural check passed — `config.sh` present, `BUILD`
present, 415 files, stagedir non-empty, launch clean, XID issued, XM RUNNING.

**[TOLD, by infra-v12, and it matches what I measured] Root cause:
`tpu_wrapper.sh:929` — when a stagedir loses its `config.sh`, the wrapper copies
in a GLOBAL DEFAULT, and that default belongs to whoever used it last.**

> ⚠️ **The lesson worth carrying: a check that asks "is X present?" cannot catch
> "X belongs to someone else." Ask instead "is this X the one this job declared?"**
> If that elt code had happened to run, we would have gotten a car that ran
> successfully and produced someone else's numbers — and we would have read them
> as our reproduction. infra-v12 adopted this as rewrite constraint C5.

### Consequence for your judgement
**Neither failure says anything about whether the port is correct.** Do not treat
"two failed launches" as evidence against the code — the code was not in either
car. The porting question is still completely untested.

---

## 9. SCHEDULER IS DOWN (as of 15:28Z) — do not submit

infra-v12 (`20260828-141921-a3218cba`) stopped the whole scheduler to rewrite the
job-record structure and the resume mechanism. **[TOLD]**

- Queue is **not dispatched**; new submissions go nowhere. **Do not enqueue.**
- Jobs already in XM keep running; nothing was cancelled.
- **Our two keys are registered as a hard constraint** (`config=remote_run_config`,
  `bucket=/cns/is-d/home/qiaos/lyy_parcae_runs`) and so is `allowed_metros=['cbf']`.
  They promised these survive archive + migration, so **do not re-add them by hand**.
- 🔴 **The maintaining sentinel has been STOPPED** on their instruction (pid
  1370666, confirmed gone, 0 residual instances). **[RAN]** Until the scheduler is
  back, nothing of ours writes to the queue.
- ★ **They have asked for radio silence** — no receipts, no status updates. Only
  contact them if you see something actively causing loss, or if they ask.
  Otherwise write it here; they will read it after the restart.

### Snapshot taken just before archival
`~/work/.parcae_torch_watch/PRE_ARCHIVE_SNAPSHOT.txt` holds the full entry as of
15:25Z with an md5 fingerprint. **Compare against it after migration** — that is
the cheapest way to catch a field silently dropped in the rewrite.

### First things to do when the scheduler comes back
1. Diff the migrated row against `PRE_ARCHIVE_SNAPSHOT.txt`; check `config`,
   `bucket`, `allowed_metros` specifically.
2. **Only if a key is missing**, restart the sentinel via `restart_sentinel.sh`.
3. Before the next launch, verify the stagedir's `config.sh` names OUR target,
   not just that it exists (see §8).
