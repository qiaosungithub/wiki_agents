# STATE-SYNC / HANDOFF: golden-heron (RNN research v4) → next independent session
Written 2026-08-28 ~02:09Z by golden-heron. Reason: operator wants v4 as an INDEPENDENT
top-level session, not a subagent of chatty-bot. A fresh session will take over.

**READ ORDER for the taker-over:** (1) this file, (2) `HANDOFF_v3_to_v4.md` (same dir —
v3's full handoff: environment, science, rules). Together they are sufficient to resume
with zero context loss. Also `../MEMORY.md` (direction layer) + `AUTORESEARCH_LOG.md` tail.

Copy of this file also at `$AMPLY_ARTIFACT_DIR/HANDOFF_v4_state.md` (run id
20260827-020128-ca2b125d) plus all fix backups (see §7).

---
## 0. ONE-LINE STATUS
dyn-precision bug: FOUND + PROVEN (local numerical TDD) + FIXED (gated rescue) + regression-
tested (18/18, fault-injection-verified) + REPORTED to operator (Chinese, via chatty-bot).
FIXED sweep fully STAGED on the box in an isolated `rnn_unroll_v4` dir, tests 18/18 on the box,
NOT launched. **Awaiting operator decision: kill the poisoned idea_sweep2 + launch the FIXED
sweep, vs let idea_sweep2 finish for the record.** Standing by; no destructive ops pending.

---
## 1. THE dyn-prec BUG (operator's explicit first task — DONE)
Operator's intuition ("我感觉肯定有 bug,彻查") was CORRECT.

### Root cause (the killer, = v3's bug candidate #1)
The rescale hook is registered on EVERY retained hidden state h_t. In train.py's dyn-prec-ON
path, `loss.backward()` fills the STANDARD param grads (W_ih, b, W_hh, readout) by summing
`dL/dh_t · dh_t/dparam` ACROSS timesteps, backpropped THROUGH those hooked h_t. A per-timestep
rescale scalar c_t does NOT cancel in that cross-timestep sum → it arbitrarily re-weights each
timestep's contribution → CORRUPTS the real param-grad DIRECTION. The docstring's "normalization
discards magnitude → no-op" safety argument only ever covered the per-site delta grads g_t (which
the unroll optimizer normalizes); it forgot the real params ride the same hooks. Corrupted W_ih/b
can't learn marker→accumulation → model sits on the memoryless plateau 0.167. Matches the symptom.

### Numerical proof (local TDD, CPU, T=200, np0.5 arm norm_power=0.5)
cos(param grad dyn-prec ON vs clean OFF):
  - readout.weight / readout.bias = **+1.000000**  ← CONTROL: readout branches off UPSTREAM of the
    h_T hook, so it's unaffected → this proves the test is faithful, not a coding artifact.
  - **W_ih = +0.672, b = +0.682, W_hh = +0.720**  ← CORRUPTED (~48° off true direction).
  - magnitudes also inflated ~50–67× (|on(W_ih)|≈29 vs |off|≈0.52).
Secondary bugs also confirmed:
  - #2 per_sample=True (old DEFAULT): per-ROW rescale reweights the batch sum → changes merged g_t
    DIRECTION (T200 norm_power=1.0: cos(persampleTrue,OFF)=0.929 vs persampleFalse=0.966).
  - #3 partial norm_power=0.5 (the actual np0.5 arm): rescue scalar leaks into merge even with a
    single global scalar (cos≈0.87 to clean).

### The red flag that started it (v3 found): SAME arm, dyn-prec the ONLY diff
np0.5 lr1e-4 T200 60k fp64: dyn-prec OFF (t200_3arm) → 3/8 solve; dyn-prec ON (idea_sweep2) → 0/4
all stuck at 0.169. → the whole dyn-prec-ON regime was poisoned.

---
## 2. THE FIX (gated rescue) — 3 files changed, all LOCAL at ~/work/rnn_unroll/
### dynamic_precision.py
- Added module gate `_RESCUE_ENABLED: bool = False` (default = hooks are NO-OPS).
- Added `@contextlib.contextmanager def rescue_active()` that flips the gate True for its body.
- `_make_rescale_hook`: hook now returns `grad` unchanged when `not _RESCUE_ENABLED` (dormant).
- **Changed default `per_sample=True → per_sample=False`** in `attach_dynamic_precision_hooks`
  (a single per-timestep scalar is the only rescale that provably preserves g_t direction).
- Rewrote the docstring to explain the gate + why (paths (a) g_t extraction vs (b) real params).

### train.py (unroll branch, `if want_hs_eff:` block, ~lines 239–259)
- `from dynamic_precision import attach_dynamic_precision_hooks, rescue_active`
- Wrapped ONLY the site-grad extraction in the gate:
      with rescue_active():
          site_grads = list(torch.autograd.grad(loss, deltas, retain_graph=True))
      for _h in hs:      # drop the RESCUED hs.grad the line above stored via retain_grad hooks
          _h.grad = None
      loss.backward()    # rescue DORMANT here → TRUE param grads + TRUE (vanishing) hs.grad for probe
- Net: early g_t still revived (operator idea-1 intact) BUT params get their TRUE, uncorrupted grad;
  and the depth probe reads the true vanishing curve (the hs.grad reset also fixes a diagnostic
  contamination that existed in the OLD code too).

### test_dynamic_precision.py (NEW, 6 tests)
Replicates train.py's ON path faithfully. Key tests: gate-dormant-by-default; **param-grads-
uncorrupted-under-dynprec-on** (all 5 params cos=1.0, rel-err<1e-9 vs clean OFF — the killer);
rescue-revives-early-site-grads (90→199/200 nonzero @T200); rescue-preserves-true-site-direction;
hidden-grad-probe-stays-true-vanishing; per_sample=False-preserves-merged-direction-better.

### Verification (local + on box)
- Fixed path: all 5 param grads cos=+1.00000000 vs clean OFF; sites revived 90→199/200, earliest
  |g_t| ~1e-44 → O(1) with TRUE direction preserved.
- FAULT-INJECTION: restored the OLD unconditional hook → 3 tests FAIL (gate-dormant, param-grads-
  uncorrupted, hidden-probe-true-vanishing); 3 common-behavior tests pass. So the tests genuinely
  catch the bug. Then restored the FIXED file (md5 round-trip clean).
- FULL local suite **18/18** (6 test_unroll + 6 test_unroll_optimizer + 6 test_dynamic_precision).
  Local python: miniforge `python3` with torch 2.13.0+cpu (v3's `.venv` at ~/work/rnn_unroll/.venv
  is GONE locally; the BOX still has its own venv). Run: `CUDA_VISIBLE_DEVICES="" python3 -m pytest -q`.
- train.py smoke, all 4 arms (truestate/np0.5/spectral/selective), dyn-prec ON, CPU tiny: loss moves,
  no nan (e.g. np0.5 T30 40step 0.59→0.28; truestate 0.41→0.19).
- The two `scripts/diag_*.py` (diag_evolution.py, diag_gradmag.py) were updated to wrap their
  site-grad measurement in `rescue_active()` (else they'd now silently measure NON-revived grads).

---
## 3. STAGED FIXED SWEEP on the box (NOT launched)
- Box: `deepflow-4a100-40gb-junhwahur-1`, zone us-central1-b, project viscam-cloud, 4×A100.
- Created `~/work/rnn_unroll_v4` = `cp -r` of the RUNNING `~/work/rnn_unroll_v3` (so it inherits the
  EXACT running code + the `.venv` symlink → /home/qiaos/work/rnn_unroll/.venv). Then OVERLAID the 3
  fixed files (dynamic_precision.py, train.py, test_dynamic_precision.py) + the launcher
  `scripts/run_idea_sweep_fixed.sh`. This did NOT touch rnn_unroll_v3 (the live sweep dir).
- **Line-by-line diff proof**: pulled the box's RUNNING v3 train.py and diffed vs my fixed local
  train.py → the ONLY differences are my dyn-prec edits (import line + gated block). No accidental
  reversions. Also confirmed box v3 dynamic_precision.py = OLD unconditional hook (0 gate) → idea_sweep2
  IS poisoned, with certainty.
- **Box test run: 18/18 pass** via `cd ~/work/rnn_unroll_v4 && CUDA_VISIBLE_DEVICES="" .venv/bin/python
  -m pytest -q test_unroll.py test_unroll_optimizer.py test_dynamic_precision.py`. (NOTE: do NOT run
  bare `pytest -q` on the box — v4 inherited stray v3 scratch files like `dyn_test.py` that grab CUDA
  at import and break collection under CUDA_VISIBLE_DEVICES=""; name the 3 real test files explicitly.)

### run_idea_sweep_fixed.sh — what it does
Same as v3's run_idea_sweep2.sh but: `cd ~/work/rnn_unroll_v4`, GROUP="idea_sweep_fixed",
SCHED="logs_idea_sweep/_schedF.log", run_name prefix "ISF_", ALL-DONE marker "idea_sweep_fixed ALL DONE".
Arms: {truestate(--unroll_true_state 1 --true_state_flavor adamw), np0.5(--norm_power 0.5),
spectral(--norm_kind spectral), selective(--selective_sites 1 --sel_n_random 2 --sel_n_last 2)}
× lr{1e-4,3e-4} × seed{0..7} = 64 runs, SEED-OUTER, 12 lanes (3/GPU).
COMMON="--wd 0.0 --dtype float64 --norm_eps 1e-38 --dyn_prec_eps 1e-300 --unroll_sqrt_divisor nonzero
--optimizer adamw --hidden 128 --batch_size 128 --eval_every 400 --log_every 800 --probe_every 100000
--T 200 --steps 60000". dyn-prec is AUTO (=-1) → resolves ON for unroll (the launcher doesn't pass
--dynamic_precision, so it gets the fixed gated ON path). `bash -n` OK locally.

### EXACT commands to launch the FIXED sweep (once operator approves)
```
# 1. (if killing the poisoned sweep first) find + kill the v3 sweep procs by EXPLICIT PID:
#    on box: pgrep -f "run_name IS_"   → kill those PIDs  (do NOT pkill a pattern matching your shell)
#    also kill the v3 scheduler if the run_one lanes would relaunch (check _sched2.log tail).
# 2. clear v4's INHERITED old logs so the tally is clean:
gcloud compute ssh qiaos@deepflow-4a100-40gb-junhwahur-1 --zone=us-central1-b --project=viscam-cloud \
  --command 'cd ~/work/rnn_unroll_v4 && rm -f logs_idea_sweep/_schedF.log logs_idea_sweep/ISF_*.log; rm -rf wandb/run-*'
# 3. launch (backgrounded so the SSH channel doesn't hang — the >log 2>&1 </dev/null is REQUIRED):
gcloud compute ssh qiaos@deepflow-4a100-40gb-junhwahur-1 --zone=us-central1-b --project=viscam-cloud \
  --command 'cd ~/work/rnn_unroll_v4 && setsid nohup bash scripts/run_idea_sweep_fixed.sh >/tmp/isf.out 2>&1 </dev/null & disown; echo LAUNCHED'
# 4. verify ~15s later: pgrep -f "run_name ISF_" | wc -l   (expect ~12)
```
Filter the SSH banner with: `grep -vE 'store now|openssh|post-quantum|Recommend|tunnel|WARNING|vulnerable|upgraded|Warning: Permanently|troubleshoot'`.

---
## 4. LIVE STATE (as of 02:09Z 2026-08-28)
- **idea_sweep2 RUNNING (POISONED, dyn-prec ON old hook)**: 18/64 done, 13 live procs, 4×A100 ~99%.
  All finished runs still on the memoryless plateau (~0.169). Dir ~/work/rnn_unroll_v3, group
  idea_sweep2, sched logs_idea_sweep/_sched2.log. Its 0/N is NOT a fair verdict on the unroll ideas
  (poisoned) — per rule 9 (跑完前不下结论) do not cite it as such; it's at most a record of "arms
  under the buggy dyn-prec".
- **Watchers (3 running LOCALLY in /tmp, all currently ping SID="golden-heron" = ME):**
  - `/tmp/sheet_up2_quiet.sh` (writes sheet rows 99-106; pings only on ALL DONE)
  - `/tmp/w_is2_quiet.sh` (pings only on ALL DONE with final tally)
  - `/tmp/trig_is2.sh` (pings on first SOLVE / half / first completion)
  ★ **The taker-over MUST re-take-over these**: edit each `SID="golden-heron"` → your OWN session id
  and restart (kill by explicit PID first, then `setsid nohup bash /tmp/<f> >/tmp/<f>.out 2>&1 </dev/null &`),
  OR kill them and poll wandb yourself. They hardcode `export AMPLY_RUN_ID=20260827-020128-ca2b125d`
  (this run) — a new run id may need updating too, else notify can't find the worker.
- **chain_1nfix.sh: KILLED and intentionally NOT relaunched.** It auto-launched ANOTHER dyn-prec-ON
  sweep (the corrected 1n/1n² poly*_late arms) after idea_sweep2 drained — but that would run under the
  SAME buggy dyn-prec (rule 8: 1/n MUST have dyn-prec ON). Hold it until after the fix ships; then its
  arms belong in a FIXED-dyn-prec sweep, not the buggy one.

---
## 5. PENDING OPERATOR DECISIONS (pivots — operator drives)
1. **[main] kill poisoned idea_sweep2 + launch FIXED sweep (my recommendation), vs let it finish for
   the record.** I recommended killing (continuing burns 4×A100 on known-poisoned runs). Commands in §3.
2. After the FIXED sweep: whether to also run a dyn-prec-OFF control (4 arms) as a third condition —
   but note np0.5 dyn-prec-OFF already = 3/8 in t200_3arm, and the FIXED dyn-prec IS the operator's
   intended condition, so the primary comparison is FIXED-dyn-prec arms vs baseline 2/8 (Fisher p).
3. Whether/when to relaunch the corrected 1n/1n² (poly*_late) arms — now under FIXED dyn-prec.
4. (older, from v3) whether to git-commit the wiki_agents MEMORY files (repo had 11 others' uncommitted
   edits, so v3 did NOT commit) — low priority.

---
## 6. OPERATOR'S STANDING RULES (obey; full list in MEMORY.md §2 / v3 handoff §6)
Chinese to operator. Mid-run = FACTS ONLY, no verdicts until a sweep fully completes (rule 9,
"跑完前先不出结论"). TDD: local test before any remote job. Report cadence: silent on heartbeats;
proactively message operator only on (a) first SOLVE, (b) an arm reaching n≥4 for a trend readout,
(c) ALL DONE, (d) a significant finding (like this bug). Don't change T/steps unless baseline
saturates (T200 still discriminating, baseline 2/8=25%). truestate base optimizer = adamw (NOT
atan2). depth_weight = poly*_late (last loop weight 1). Metric = solve-rate over 8 seeds + Fisher
exact p vs baseline 2/8. GPU serial/non-preemptible plain procs. SSH flaky → short single-purpose
cmds + retry; box python3 has no pyyaml (parse config.yaml with regex). pkill self-match trap → use
explicit PID. Notify: `~/.amply/bin/amply_notify <SID> "msg"` (NOT $AMPLY_NOTIFY — ACL-blocked).

---
## 7. ARTIFACTS (backups; run id 20260827-020128-ca2b125d)
In `$AMPLY_ARTIFACT_DIR` (= /usr/local/google/home/qiaos/.amply/artifacts/20260827-020128-ca2b125d):
- DYNPREC_BUG_FIX_SUMMARY.md — the fix summary (root cause, proof, fix, verification).
- dynprec_wiring_analysis.md — the gradient-path analysis (which params corrupted & why).
- diag_dynprec_bug.py — the numerical diagnostic (proof + fix prototype; monkeypatch-gated).
- dynamic_precision.py.orig (buggy) / dynamic_precision.py.fixed ; train.py.fixed ;
  test_dynamic_precision.py — backups of the fixed files.
- HANDOFF_v4_state.md — copy of THIS file.
The AUTHORITATIVE fixed code is LOCAL at ~/work/rnn_unroll/ (dynamic_precision.py, train.py,
test_dynamic_precision.py, scripts/run_idea_sweep_fixed.sh) AND staged on the box at
~/work/rnn_unroll_v4/. AUTORESEARCH_LOG.md + MEMORY.md updated with the bug+fix.

---
## 8. HANDOFF LOGISTICS (what the new session should do first)
1. Read this + HANDOFF_v3_to_v4.md. 2. Re-take-over the 3 /tmp watchers (repoint SID to your id;
update AMPLY_RUN_ID if your run id differs). 3. Confirm the pending decision (§5.1) with the operator
before any kill/launch. 4. Do NOT kill idea_sweep2 or launch the FIXED sweep until the operator says so.
5. When you launch or conclude anything: update AUTORESEARCH_LOG.md + MEMORY.md + the spreadsheet
(EqR workbook 17pvrMbOKOKFiIa-eorO8Od12qc5JmrFCSXcXKeoe_u0, tab "RNN-unroll-adding (qiaos)",
idea_sweep2 block rows 99-106; add a new block for idea_sweep_fixed).

---
## 9. UPDATE (02:15Z 2026-08-28) — session transfer + SECOND machine
**This doc is being handed to a NEW INDEPENDENT top-level run** (not a subagent):
- **New session: RID `20260828-021328-ef5771b7`, title "RNN research v4"** (chat-only top-level run;
  operator talks to it directly in the dashboard). It is a DIFFERENT amply run from golden-heron
  (RID 20260827-020128-ca2b125d), so golden-heron and chatty-bot CANNOT `send_message` it — cross-run.
- golden-heron (me) is in HANDOFF MODE: still alive, NOT retired, NOT killing idea_sweep2, no
  destructive ops. The 3 /tmp watchers still ping SID="golden-heron". **New session: re-take-over the
  watchers** — edit each `/tmp/{sheet_up2_quiet,w_is2_quiet,trig_is2}.sh`: set `SID="<your session id>"`
  AND `export AMPLY_RUN_ID=<your RID = 20260828-021328-ef5771b7>` (BOTH — notify needs the right run id
  to find your worker), then kill-by-PID + restart (`setsid nohup bash /tmp/<f> >/tmp/<f>.out 2>&1 </dev/null &`).

**SECOND MACHINE added by operator (for parallel sweeps):**
- **`qiaos-4a100`**, zone **us-central1-f**, project viscam-cloud, **4×A100-SXM4-40GB, on-demand**.
- FRESH DLVM: **no rnn_unroll code, no venv yet**; system torch is **2.9.1+cu129** (newer than the
  original box). Needs code rsync + a venv (or use system torch) before it can run.
- Operator's usage: **split by sweep, one scheduler per machine, don't oversubscribe.** Natural split:
  **one machine runs dyn-prec-ON (the FIXED sweep, idea_sweep_fixed), the other runs the dyn-prec-OFF
  control** (same 4 arms) → the fair ON-vs-OFF comparison comes out simultaneously.
- Original box stays `deepflow-4a100-40gb-junhwahur-1` (us-central1-b) — currently running the POISONED
  idea_sweep2 and holding the staged rnn_unroll_v4 FIXED sweep.
- ⚠️ golden-heron will NOT set up qiaos-4a100 (avoid two "v4"s colliding). The NEW session owns machine
  setup + the ON/OFF split.

**Net plan the new session should confirm with operator, then execute:**
1. Re-take-over the 3 watchers (§4 + above). 2. Confirm the pivot (§5.1): kill poisoned idea_sweep2?
3. Launch the FIXED sweep (idea_sweep_fixed) on one machine (commands in §3), and a dyn-prec-OFF control
   sweep (4 arms) on the other. 4. One watcher per sweep, pointed at your session id + your RID. 5. On
   completion: solve-rate per arm + Fisher p vs baseline 2/8; update AUTORESEARCH_LOG + MEMORY + sheet.
