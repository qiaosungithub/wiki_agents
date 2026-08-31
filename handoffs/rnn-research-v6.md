# HANDOFF: rnn-research-v6 (run 20260829-034151-9016fd7a)

Took over 03:41Z 2026-08-29 from v5 (20260828-143741-000ab3d8, died on a
pyspanner oversized-value write). Line = RNN unroll / adding problem, gradient
propagation science. Project guide: `../projects/rnn_unroll_adding.md`.

## 0. THE ONE LESSON WORTH CARRYING FORWARD
**"读数是真的,但测的是别的东西" — the reading is real, but it measures the
wrong object.** I hit this twice in one day, in two unrelated forms, and it is
the failure mode that survives review because the number is reproducible:

| instance | what I reported | what it actually measured |
|---|---|---|
| `cos(spectral, np1.0)=+0.81` cited as evidence that spectral behaves like full L2 normalization | a property of our 40-order vanishing gradient profile | the random-matrix constant `8/(3π)=0.8488` — identical on iid Gaussians with NO decay structure (re-measured: 0.8405). Same for "last-10 energy share 4.47" = `sqrt(200/10)`, the merge's own `1/sqrt(C)` divisor ratio. |
| watcher reporting `AGE=25332s` for box1 | the T=300 sweep had stalled 7h | the watcher was still pointed at `logs_fixed` (the COMPLETED T=200 dir); the T=300 sweep writes `logs_T300` and was perfectly healthy |

### The sibling failure: 命令返回成功但没做成事 — the call succeeded, the work did not
Same family, opposite direction: above, a real reading of the wrong object;
here, a real success code covering an action that never happened.

| instance | what said OK | what was actually true |
|---|---|---|
| `kill` then `kill -9` on the T=300 procs, both returning cleanly | 13 训练进程已停 | `pgrep -f "run_name FIX_T300_"` through an SSH `--command` layer never matched (quote/escape mangling), so the PID list was EMPTY and kill looped over nothing. GPUs stayed at 25-32%. |
| `LAUNCHED` / `ISSUED` echoed by a backgrounded launcher | the sweep is running with my flags | only that the shell reached `echo`. Verified instead by reading `/proc/<pid>/cmdline` (flags) and `/proc/<pid>/environ` (thread caps). |

### The third form, and the worst: 失败留下的痕迹长得像成功
Collected from two other lines the same day; the rule is general, and this form
is more dangerous than the two above because it manufactures positive evidence.

| instance | what looked fine | what was true |
|---|---|---|
| a write to an over-quota / personal-ceiling CNS bucket | the output file EXISTS | it is 0 bytes — the loss looks like a success artefact |
| `blaze build` in a shared workspace | build succeeded, no error | `blaze-bin`'s second hop was republished by another workspace's build; the artefact is not where you look. Watch the absolute `blaze-out/k8-fastbuild/bin/...` path, never `blaze-bin` |
| a metro that falls back to a personal bucket | no SystemExit, the job launches | it silently writes to a poisoned personal quota |

**Existence is not completeness** — check size, content and mtime, never just
presence. The first two forms need you to go looking; **this one hands you a
forged receipt.** Confirmed independently three times in one shift across
different lines: a 0-byte output file, a `blaze-bin` hop repointed by another
workspace, and a `list_artifacts` call returning empty for artifacts that
existed.

**Rule: verify a destructive or state-changing action at the FAR END, in a unit
the action cannot fake.** For a kill that is GPU utilisation dropping to 0% and
VRAM released — not the return code. For a launch it is `/proc/<pid>/cmdline`,
not the echo. When a pattern-match feeds a kill list, print the list first: an
empty list and a successful kill look identical.
Corollary already burned into this line: **never `pkill -f`** (it matches the
shell running it), and do not trust `pgrep -f` inside `ssh --command` either —
iterate `/proc/[0-9]*/cmdline` and match there.

**Detector, cheap and general: ask what the number would read with the structure
REMOVED.** If it returns the same value on iid noise, or on a directory with no
live job, it is measuring the instrument. Corollary for watchers: a probe must
name the directory AND the run-name prefix of the sweep it claims to watch, and
a failed probe must say UNREADABLE — never 0, which is indistinguishable from a
real wipeout.

## 1. SCIENTIFIC RESULT (T=200, all cells 5 seeds, 126 runs finished)
**TRUE TBPTT beats full BPTT decisively.** `--tbptt_k` detaches h at t=T-k so
the backward graph physically stops; the FORWARD pass still runs all T steps.
Proven numerically (`/tmp/tbptt_proof.py`): with x.requires_grad, early-timestep
`|dL/dx|` is EXACTLY 0.0, and all four param grads match a hand-rolled
"last-k-steps-only" computation to 0.000e+00. It is not the old `--site_mask_k`
(which truncated W_hh alone and let W_ih/b/readout keep full-horizon credit).
`ttbptt*` arms run `mode=baseline`, no unroll machinery, dyn-prec OFF.

Solve rate (FINAL@60k, the strict criterion — identical to BEST for these arms):
| arm | lr1e-4 | lr3e-4 | lr1e-3 |
|---|---|---|---|
| k=1 | 0/5 | — | — |
| k=3 | 0/5 | — | — |
| k=10 | **5/5** | **5/5** | **5/5** |
| k=30 | **5/5** | **5/5** | 0/5 |
| k=100 | **5/5** | 0/5 | 0/5 |
| full BPTT (baseline) | 0/5 | 0/5 | 0/5 |

- **It is a (k, lr) interaction, NOT an inverted-U in k.** I predicted large k
  would degrade toward baseline; k=100 came back 5/5 and refuted it. Larger k
  accumulates a larger gradient, so effective step size grows with k: large k
  needs a smaller lr. k=10 is special only in being the most lr-ROBUST.
- **Weight-sharing rule export is PROVEN, not argued.** A network reading only
  marker2 has a hard MSE floor of Var(v1)=1/12=0.0833 (closed form + MC agree).
  marker1 is never inside the trainable window for any k<=100, yet k=10/30/100
  are all 5/5 strictly BELOW 0.0833. Breaking that ceiling is arithmetically
  impossible without reading marker1 ⇒ the timestep-invariant rule learned from
  in-window markers is exported by weight sharing to zero-gradient timesteps.
- Supervision starvation explains the small-k end: P(marker in window)=k/200,
  so k=1 gives ~1.3 marked samples per 128-batch. Clean dose-response
  k=1 (no escape) → k=3 (0.0924-0.1468, partial) → k=10 (solves).
- Pre-registered verdict is the GOVERNING one: per-cell Holm across 23 cells
  = 0.3753 ⇒ "suggestive, needs +8 seeds". NOT a WIN. Do not switch to the
  pooled Fisher (p=2e-08) to win the argument.
- **Retracted**: "truncation rescues the fatal np=1.0 rule". Under FINAL@60k
  `tt_unroll10` is 0/5 (was 2/5 under BEST) — it dips into the solve band then
  degrades. Only the strong form is retracted; np=1.0+trunc does briefly reach it.
- Literature (3 read-only sub-agents, artifacts `LITREV_[ABC]_*.md`): no
  published vanilla-tanh RNN solves adding at T>=200 (Arjovsky/IndRNN/Vorontsov
  all report failure) — our full-BPTT 0/5 REPRODUCES their negative. The
  inverted-U in k is published (Metz'21, Aicher'19) but their left arm is always
  "window shorter than task memory"; ours is k=10 << memory span and solves.
  "Rule export" has no name in the temporal setting; nearest named prior art is
  phantom gradient (Geng'21) / JFB (Fung'21), both for implicit/DEQ models.

## 2. LIVE STATE at 14:25Z
- **box1** `deepflow-4a100-40gb-junhwahur-1` (us-central1-b), dir
  `~/work/rnn_unroll_v4_fix`, **T=300 sweep RUNNING**: naive TBPTT
  k{10,30,100} x lr{1e-4,3e-4,1e-3} x 5 seeds + full-BPTT control 3lr x 5
  = 60 runs x 60k steps, launcher `run_T300.sh`, jobs `jobs_T300.txt`,
  logs `logs_T300/`, group `T300_20260829`, 12 lanes, ETA ~8h from 14:00Z.
  Operator's standing order: **if T=300 saturates too, go straight to T=500 —
  no need to ask.**
- **box2** `qiaos-4a100` (us-central1-f), dir `~/work/rnn_unroll_f_fix`,
  16 leftover T=200 unroll runs (tt_unroll*, truestate) still draining.
- **watcher** `/tmp/w_rnn_v6.sh`, 20-min self-wake, ppid=1, messages hard-capped
  at 600 chars. Points at BOTH boxes with the CORRECT logdir+prefix per box.
- Compute is plain processes on GCE boxes — no Borg/XM/CNS, `jobs.md` does not
  apply; infra store windows do not affect this line.

## 2a. PRE-REGISTERED PREDICTION for the T=300 sweep (written 15:35Z, BEFORE the data)
Recorded before waves 3-5 landed so it cannot be rationalised afterwards.

**Hypothesis (from T=200):** what a run needs is not a particular k or a
particular lr, but an effective step size matched to the WINDOW FRACTION k/T.
T=200 k=10 (5%) solved at all three lrs; T=300 k=10 (3.3%) collapsed to 0/5 at
lr1e-4 and 3/5 at lr3e-4 (FINAL@60k). If the hypothesis is right, restoring the
window fraction by raising k should restore lr1e-4.

**The falsifiable call, with its criterion fixed in advance:**
> **k=100 @ lr1e-4 at T=300 (window fraction 33%) SHOULD SOLVE — i.e. >=3/5
> under FINAL@60k, solve threshold 0.05.** k=30 @ lr1e-4 (10%) should land
> between k=10's 0/5 and k=100's result.

**If it does not solve, report it as a refutation.** Do not rescue the
hypothesis by switching to BEST-over-run, lowering the seed bar, calling the
cell "incomplete", or re-reading 0.05. The criterion above is the whole
criterion. Precedent on this line: the `cos=+0.81` retraction and the
`tt_unroll10` 2/5->0/5 retraction both happened because the criterion was fixed
first and the number was allowed to fail against it.

**★ An observation window must be LONGER than the phase it claims to judge —
this is a statistical criterion, not just a liveness check.** On this task,
solving happens at 50k-60k of 60k steps (recorded solved_at: 49200 51600 56400
57600 59200). So a mid-run reading taken at 33k/60k sits BEFORE the window in
which the outcome is decided, and its evidential value is ~zero — in EITHER
direction. I learned this by getting it wrong first: at 46-49k I called k=30
"trending against my hypothesis", and on completion it was fully separated from
k=10 (all 5 seeds lower, Mann-Whitney p=0.0040). One round later, with k=100
flat at 0.1577-0.1582 at 33k, the correct move was to calibrate that reading
against the earlier mistake rather than repeat it. **Discipline is symmetric:
do not concede early on an unfavourable partial, and do not hint at a
turnaround on a favourable one.** State that the window cannot yet see the
effect, and wait for FINAL@60k.
(This is the time-form of the same trap as "the reading is real but measures
the wrong object": here the reading is real but measures the wrong PHASE.)

**Scope discipline:** "lr1e-4 fell from 5/5 to 0/5 at T=300" is a statement
about **k=10 only**. At the time it was measured, waves 3-5 (k=30, k=100,
full-BPTT baseline) had not started. Never quote it as a statement about TBPTT
in general.

## 2a-RESULT (17:14Z): the prediction in §2a was REFUTED. Read this with it.
**k=100 @ lr1e-4 at T=300 = 0/5** (FINAL@60k; finals 0.1083 0.1668 0.1668 0.1669
0.1669, four of five AT the memoryless floor 1/6). Criterion was >=3/5. None of
the four escape hatches was used.

**★ Both of my successive stories were over-fitted to whichever T was in front
of me.** In the morning, on T=200, I ABANDONED an inverted-U-in-k story and
replaced it with a pure (k, lr) scale account — because T=200 showed
k=10/30/100 all at 5/5 under lr1e-4, i.e. no structure. That "refutation of the
inverted U" was a **null result obtained on a saturated cell**: T=200 was too
easy, and the ceiling hid the structure. At T=300 the same axis reads 0/5, 1/5,
0/5 (medians 0.1596, 0.0916, 0.1668) — an inverted U with a peak at k=30 and
both ends back at the memoryless floor, which no pure scale effect can produce.
**A negative result from a saturated cell is not evidence of absence.** Before
concluding "no structure here", check whether the cell can express structure at
all — a 5/5-everywhere row has no dynamic range left to show one.

**★ The inverted U is now a PHENOMENON, not an explanation.** Two mechanisms are
established at the ENDS (small-k supervision starvation, P(marker in window)
= k/T; and the k-lr scale effect, which is real and reproduces across T: best lr
falls as k rises). Neither predicts a peak in the middle. **I do not have a
mechanism for the k=30 peak and did not invent one.** Leave it stated as an
open phenomenon.

**Unaffected by this refutation** (different claims, different evidence):
truncation beating full BPTT is a CONTROLLED comparison (T=200: k in {10,30,100}
5/5 vs baseline 0/5, both criteria), and rule export is a derived ceiling
argument (1/12 = 0.0833). Neither rests on the shape of the k-curve.

## 2b. THE CPU-OVERSUBSCRIPTION TRAP (cost 12.8 h if unfixed)
The launchers set NO thread cap, so each of 12 concurrent runs grabbed ~400%
CPU on a 48-core box (load 112, 2.3x oversubscribed). **GPUs sat at 26-32%
waiting on CPU.** Adding `OMP_NUM_THREADS=2 MKL_NUM_THREADS=2
OPENBLAS_NUM_THREADS=2` in front of the `train.py` invocation took GPUs to
98-99%, load to 21, and per-run throughput from 307 to 1440 steps/min = **4.7x**
(T=300, 60 runs: 16.3 h -> 3.5 h). A same-conditions A/B on 200 steps predicted
only 1.6x; the gap is real, not an error — the A/B removes one process's
oversubscription, capping ALL lanes removes the mutual contention as well.

**The fix lives in the launcher, so it dies with the launcher.** Two guards, both
in `~/work/rnn_unroll_v4_fix/`:
- `run_T500.sh` was derived from the RUNNING `run_T300b.sh` by sed, so it
  inherits the caps instead of relying on anyone remembering them.
- `preflight.sh <launcher>` refuses any launcher missing all three caps.
  Fault-tested: it PASSES run_T300b/run_T500 and FAILS the old uncapped
  run_T300.sh. **Run it before every launch.**
Symptom to recognise later: GPU utilisation well under 90% while `uptime` load
exceeds core count. Check that before concluding a sweep is simply "slow".

## 3. OPERATING RULES THAT COST ME SOMETHING
- **Never `pkill -f <pattern>`** — it matches the shell running it. I killed my
  own command this way (fleet's 7th time today). Iterate PIDs and verify.
- **`LAUNCHED` is not evidence.** After every launch, read
  `/proc/<pid>/cmdline` and confirm the actual flags (`--T`, `--tbptt_k`,
  `--steps`). `pgrep -af` for this is itself a trap: the pattern matches your
  own grep.
- Requests needing approval go **in the message, one line** — never only in a
  document. A monitor's recap does not scan artifacts.
- Report to the monitor <200 words; long content = absolute path + md5 + one
  line. Resolve the current monitor at read time, never memorise the rid:
  `grep -a "# THIS MONITOR" ~/work/.monitor_watch/runs.txt | grep -oE "20260[0-9]{3}-[0-9]{6}-[0-9a-f]{8}" | head -1`
  — and if its worker is dead, find the newest live `worker_address.json`.
- Never write a large value in one storage write (v5 died of it).
- **A speedup that changes the numbers is not a speedup.** Every perf change on
  this line must prove numerical equivalence in fp64 (max abs diff ~0 on outputs
  AND on all parameter grads) before it counts. fp64 is a SCIENTIFIC requirement
  here (gradient-underflow studies span 40+ orders); fp32/AMP is not an
  acceptable "optimization" — measure its cost if useful, never recommend it as
  the headline. Same rule retired the `tt_unroll10` claim: a number that moves
  under a stricter criterion was never a result.
- `train.py` saves NO checkpoint, so "best eval over the run" is oracle early
  stopping. Report **FINAL@60k**; quote BEST only alongside it.

## 4. ARTIFACTS (all in `~/.amply/artifacts/20260829-034151-9016fd7a/`)
`K_SWEEP_FINAL.md` (the k-curve + strict-criterion addendum + the retraction
caveat, inline), `RULE_EXPORT_PROVEN.md` (the 1/12 ceiling proof),
`TBPTT_MECHANISM.md`, `TRUE_TBPTT_5of5.md`, `SPECTRAL_IS_FULL_NORM.md` (read
WITH the retraction), `RETRACTION_spectral_numbers.md`, `K_SWEEP_INTERIM.md`,
`LITREV_A_tbptt.md` / `LITREV_B_adding.md` / `LITREV_C_frozen_spectral.md`,
`RNN_V6_STATUS.md`. Numerical proof scripts: `/tmp/tbptt_proof.py`,
`/tmp/spec_dir_probe.py`, `/tmp/cellstate.py`, `/tmp/strict.py`, `/tmp/tally_v6.py`
(pre-registered tally + `--full_n`).
