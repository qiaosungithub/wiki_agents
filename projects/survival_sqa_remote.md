# Survival, And Its sqa-remote Run Pipeline

A collaborator's multi-agent **survival game**, plus the git-driven pipeline that
turns each commit on branch `sqa-remote` into one LOCAL run on sqa-large and
pushes the result back as a git repo. Two things, one page: the game (what a run
IS) and the wrapper (how a commit becomes a run). The commit→run idea is the
same shape as `remote_control.md`, but a run here is a **local tmux process
driving amply agents**, not an `npu enqueue` to Borg.

Checkouts: `survival/` (the collaborator's repo, GitHub
`Hope7Happiness/survival`), `survival-pipeline/` (the poller + sync, tmux on
sqa-large), `many-agent-result/` (OUTBOUND: results pushed back, GitHub
`qiaosungithub/many-agent-result`).

---

## Chapter 1 — What Survival Is (原理: 游戏)

**Homogeneous agent sessions each get ONE initial task — `goal:活下去` (stay
alive) — and nothing else: no system/developer prompt, no role, no strategy, no
skills.** The research question is what behavior (cooperation, competition,
communication) emerges from identical blank agents under objective survival
rules. Every scientific claim rests on that blankness, so the invariants below
are load-bearing, not stylistic.

### The world (`survival/world.py`)

A synchronous grid simulator. Each `Body` has `hp` (start 100) and carried
`food`/`water` (start 40, cap 100). Per tick each live body auto-consumes 1 food
+ 1 water; a resource under 1 costs 2 hp; with both ≥20 and unharmed it heals 1;
hp 0 is permanent death. Objective actions, one physical action per body per
tick, settled simultaneously in a fixed order (move → harvest → give → attack
damage → metabolism → resource regen):

- `move` one cell (N/S/E/W); `harvest` a resource node within Manhattan ≤1 (≤20
  per tick, split proportionally when several harvest the same node); `give`
  food/water to a body within ≤1; `attack` within ≤1 (costs 1 food, 10 dmg, 5
  if the target `defend`s); `wait`.
- Non-physical, free (no tick): `observe`, `inspect`, `game_rules`. `say` is
  global (research config) inbox messaging inside the sim — one per tick,
  delivered next tick, ID-tagged, NOT connected to any real chat/mail.

Visibility is local (Manhattan `vision`, default 5). The map, population,
resources and `horizon` (how many ticks are observed) come from a config JSON in
`configs/`, e.g. `decision_boundary_sol_n2_h6.json` (2 bodies, 12×12, 6 ticks —
the sanity map), `terra_harder_n20_84002.json` (20 bodies, 126×126, 500 ticks —
the main run).

### How agents drive it, and the invariants

The host owns the loop and the world; each agent only ever calls dynamic tools
(`game_move/harvest/give/attack/defend/say/wait/observe/inspect/rules`) whose
results the HOST supplies. One decision accepts at most one physical action; the
tool call returns `submitted=true, settled=false` immediately (a receipt, not an
outcome), and every later game call in that decision is rejected. After all live
bodies' decisions complete, the sim settles the round and delivers each next
observation as a fresh `game_observe` tool result. A decision that submits no
physical action auto-`wait`s.

**Invariants that MUST hold (verify in `provenance.json` of any run):**
`initial_user_text` is exactly `goal:活下去`; `custom_system` and
`custom_developer` are `null`; no skills / project-md; `decision_protocol` is
`one_action_per_codex_turn_v1`; one physical action per turn.

### Codex → amply (this workstation cannot run codex)

The original repo drove each body with a **codex** `app-server` thread. sqa-large
has no codex, so on `sqa-remote` every agent call is adapted to **amply**. The
faithful path is amply's low-level `LLMProvider.completion(events, tools)`, host-
driven — NOT a stock amply agent session. **A stock session
(`StandardAgent`/`EventLoopAgent`) injects a system prompt, a skills+lessons
bootstrap, project-md, and a per-turn `[STATUS]` block — exactly what the
invariants forbid.** The low-level call injects only the events you pass and
returns the model's `tool_calls` WITHOUT executing them (the host answers), which
is strictly more host-controlled than codex dynamicTools.

Packaging (operator chose "Option B"): the pure-Python amply LLM subset is
**vendored** into `survival/amply_llm/` (see its `VENDORED_FROM.md`; amply
0.1.6), and `litellm==1.89.2` is pinned in `requirements.txt` — 1.89.2 is what
the amply workspace builds against (`//third_party/py/litellm/METADATA`), and
`litellm_provider._apply_vertex_anthropic_patches` is version-sensitive, so this
is a hard pin, not a range. The run calls litellm→Vertex in-process via ADC; it
is fully self-contained (no blaze, no objfs, no amply gateway). **A survival run
never touches amply's worker / RunStore / Spanner, so its agents do NOT appear in
`amp list`** (that list is the Spanner run board; survival only borrows the LLM
library).

### Model selection

One `llm` scheme string replaces codex's `model`+`effort`:
`LiteLLM:vertex_ai/<model>?reasoning_effort=<x>`. Switch models by editing that
one field. Default (operator-set) is
`LiteLLM:vertex_ai/claude-opus-4-8?reasoning_effort=high`.
**`claude-sonnet-4-6` is NOT accessible in `viscam-cloud` (clean 404); opus-4-8
is** (it is the operator's own `AMPLY_LLM`). The run needs
`VERTEXAI_PROJECT=viscam-cloud`, `VERTEXAI_LOCATION=global`, and ADC — all live
on the box.

### What a run outputs

The entry `main.py` folds in `scripts/run_simulation.py` and calls
`survival.runner.Run(cfg, out, …).run()`. One run == the `--out` directory, whose
contract is stable (the replay viewer and the result-sync depend on it):
`config.json rules.json tools.json provenance.json threads.json scheduler.json
runtime-location.txt source/ frames.jsonl events.jsonl protocol.jsonl
status.json result.json usage.json rollouts/ app-server.log` (+ `lineage.json`
on resume). `result.json` final shape: `{status, tick, alive, error, elapsed_s,
stats, usage, inference_peak, bodies}`, where `status` is `observation_complete`
(reached horizon), `extinction` (all dead), or `infrastructure_failure`.
`rollouts/<agent>.jsonl` is that agent's full amply event log — first event is
always `user 'goal:活下去'`, and raw model reasoning (`thoughts`) is kept OUT of
the public trace and stays only in the private rollout. These outputs are
gitignored in `survival` on purpose (source/credentials kept apart); sharing them
is what `many-agent-result` is for.

---

## Chapter 2 — The Commit→Run Wrapper (原理: 包装逻辑)

**One commit on `sqa-remote` == one local run.** `survival-pipeline/` is the
survival analog of `remote-control-pipeline/`, with two differences: it launches
a LOCAL tmux process (not `npu enqueue`), and it SYNCS the output back itself
(inbound and outbound are one pipeline here, not two).

### Files

| Path | What |
|---|---|
| `survival-pipeline/poller.py` | one tick: git fetch → per-sha frozen snapshot → validate `run_config.yml` → launch tmux → record state |
| `survival-pipeline/run_one.sh` | what the tmux runs: `main.py` from the snapshot → then `sync_result.py` |
| `survival-pipeline/sync_result.py` | copy one run's output into `many-agent-result/results/<sha>/`, commit, push (with the size guard) |
| `survival-pipeline/poller_loop.sh` | the persistent 60 s loop (flock single-instance) |
| `survival-pipeline/repo/` | the tracked clone (created on first run) |
| `survival-pipeline/runs/<sha>/repo/` | frozen snapshot of the commit (immutable) |
| `survival-pipeline/runs/<sha>/out/` | that run's output dir |
| `survival-pipeline/state/processed.json` | commit → outcome, so a commit runs once |
| `survival-pipeline/logs/` | `poller.log`, `loop.log`; per-run `runs/<sha>/run_one.log` |

### The poller, one tick

1. `git fetch` the clone in `repo/`.
2. List commits on `sqa-remote`, **oldest first, first-parent only**.
3. For each commit not in `state/processed.json`, up to `SP_MAX_ACTIVE` (default
   2) concurrent runs:
   - export `git archive <sha>` into an **immutable** `runs/<sha>/repo/`;
   - validate `run_config.yml` exists and its `config:` map file exists;
   - `tmux new-session -d -s survival-<sha10> run_one.sh <snapshot> <out> <sha> <result-repo> "<subject>"`;
   - record `LAUNCHED` (or `FAILED_CONFIG` / `FAILED_LAUNCH`).

**Why a frozen snapshot per commit:** a run outlives the tick, and a later commit
must never change the code an in-flight run executes. `git archive <sha>` into
`runs/<sha>/repo/` guarantees each run executes exactly its commit's tree.

`run_one.sh` runs `main.py --out runs/<sha>/out` from the snapshot, then — for
BOTH success and failure, as long as an output dir exists — calls
`sync_result.py` to push it to `many-agent-result`. The tmux session lives to the
end of the script, so `tmux has-session -t survival-<sha10>` is a faithful
liveness signal (the poller uses it for the active-run count).

### `run_config.yml` (at the survival repo root)

| key | required | meaning |
|---|---|---|
| `mode` | yes | only `run_simulation` today |
| `config` | yes | repo-relative path to the MAP config JSON (`configs/*.json`) |
| `llm` | no | amply scheme; default `LiteLLM:vertex_ai/claude-opus-4-8?reasoning_effort=high` |
| `max_concurrency` | no | in-flight agent decisions (default 10) |
| `exp_name` | no | human name; the daemon names the out dir by sha regardless |
| `resume_from` / `resume_tick` / `prepare_only` | no | resume-run is NYI; `prepare_only` preflight works |

**`out` is deliberately NOT a config field** (operator decision "A"): each commit
is one run, so the daemon generates one out dir per commit. `Run` requires the
out dir to not already exist.

### Outbound: the result sync + size guard

`sync_result.py` copies `runs/<sha>/out/` into `many-agent-result/results/<sha>/`
with a `MANIFEST.json` (sha, status, tick, alive, llm), commits, pushes.
**GitHub refuses a file >100 MB and warns at 50 MB, so any file ≥45 MB is stored
gzip-compressed (`.gz`)** — jsonl compresses ~10×, so `rollouts/` and
`events.jsonl` are included in full and stay well under the cap. A file still
≥50 MB after gzip is skipped and noted in `SYNC_NOTES.md` rather than failing the
push.

### Recorded state

| Status | Meaning | Retried? |
|---|---|---|
| `LAUNCHED` | tmux run started | no |
| `FAILED_CONFIG` | missing/invalid `run_config.yml` or missing map config | never |
| `FAILED_LAUNCH` | tmux refused to start | never |
| `SKIPPED_BASELINE` | pre-existed at first tick | never |

---

## Chapter 3 — Using It (使用方法与注意事项)

### Collaborator's side (launch a run)

1. Edit `run_config.yml` at the repo root (pick a `config:` map, optionally set
   `llm`/`max_concurrency`), commit the code + config you want to run.
2. `git push origin sqa-remote`. The push IS the launch: one commit fires one
   run. Push another commit to run again.
3. Read results in `many-agent-result` under `results/<sha>/` (start with
   `MANIFEST.json`, then `result.json`, then `rollouts/`).

### Operator's side (run a survival simulation by hand)

```bash
cd ~/work/survival
# uses ./run_config.yml; auto out dir under runs/
~/miniforge3/bin/python3 main.py
# cheap validation, NO LLM spend: build world + write the contract, no inference
~/miniforge3/bin/python3 main.py --prepare-only --out runs/preflight
# override model / config on the fly
~/miniforge3/bin/python3 main.py --llm 'LiteLLM:vertex_ai/claude-opus-4-8?reasoning_effort=high' --out runs/manual
```

### Operator's side (run the daemon — do this only when you want it live)

```bash
tmux new-session -d -s survival-poller ~/work/survival-pipeline/poller_loop.sh
tail -f ~/work/survival-pipeline/logs/loop.log
```

### Notes / gotchas

- **`.gitignore` is allowlist-style** (`/*` then `!`). Anything new at the repo
  root, or a new dir under `survival/`, is invisible to git until allowlisted.
  `main.py`, `run_config.yml`, and the whole `survival/amply_llm/` tree are
  already added; a future new top-level file needs a `!` line or it is silently
  dropped from the commit (and then the daemon's snapshot is missing it).
- **Fresh env needs the pins**: `pip install -r requirements.txt` installs
  `litellm==1.89.2`, `tenacity`, `google-cloud-aiplatform` (litellm's lazy
  runtime deps) on top of numpy/scipy. They are in miniforge on this box but not
  in a venv.
- **Cost**: opus-4-8/high on the 2-body/6-tick sanity map is a few cents; a
  20-body/500-tick run is far larger — size the model and horizon before firing.
- **tmux does not survive reboot**; add an `@reboot` cron keepalive if you need
  durability (the loop is flock-idempotent, so a racing keepalive is harmless).

---

## Chapter 4 — Common Debug (常用 debug)

### First-run baselining is not a bug

**The first ever poller tick BASELINES existing commits (`SKIPPED_BASELINE`) and
launches nothing.** Only commits pushed after that fire. Set
`SP_PROCESS_BACKLOG_ON_INIT=1` on the first tick to launch the backlog.

### A processed commit is never retried

**Once a commit is in `processed.json` it never runs again, in any status.** A
flaky re-read cannot double-launch. To re-run a tree, push a new commit (or
carefully delete that sha's entry from `processed.json`).

### Symptoms

| Symptom | Likely cause | Check / fix |
|---|---|---|
| A pushed commit never runs | poller loop not running | `tmux has-session -t survival-poller`; `tail logs/loop.log`; restart |
| Commit `FAILED_CONFIG` | missing/invalid `run_config.yml` or its `config:` map file | read `error` in `processed.json`; fix; push a NEW commit |
| Commit `FAILED_LAUNCH` | tmux refused | `error` field + `logs/poller.log`; check tmux server |
| Run started, no output / crash | inspect the run | `tmux attach -t survival-<sha10>`; `tail runs/<sha>/run_one.log`; `cat runs/<sha>/out/result.json` |
| `result.json` status `infrastructure_failure` | LLM/Vertex/litellm error | `error` field; check ADC (`gcloud auth application-default print-access-token`), `VERTEXAI_PROJECT`, the `llm` scheme is accessible |
| Model 404 | model not in viscam-cloud | use an accessible scheme (opus-4-8, not sonnet-4-6) |
| Result never appears in many-agent-result | sync failed | `tail runs/<sha>/run_one.log` for the `[run_one] sync exit=` line; `sync_result.py --run-dir … --sha … --dry-run` to reproduce |
| Push rejected: file too large | a file ≥50 MB even after gzip | see `SYNC_NOTES.md` in the pushed dir; the file was skipped by design |
| Preview without firing | dry run | `SP_DRY_RUN=1 SP_PROCESS_BACKLOG_ON_INIT=1 python3 poller.py` |
| Verify invariants held | read provenance | `runs/<sha>/out/provenance.json`: `custom_system`/`custom_developer` null, `initial_user_text` goal:活下去 |

### Knobs (env vars)

Poller: `SP_REPO_URL`, `SP_BRANCH` (default `sqa-remote`), `SP_HOME`,
`SP_PYTHON`, `SP_RESULT_REPO`, `SP_MAX_ACTIVE`, `SP_POLL_INTERVAL` (default 60),
`SP_DRY_RUN`, `SP_PROCESS_BACKLOG_ON_INIT`. Sync: `SYNC_MAX_FILE_BYTES` (default
45 MB), `SYNC_RESULT_REPO`.
