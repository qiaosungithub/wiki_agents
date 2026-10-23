# Next Connectionism (`~/work/next-connectionism`)

Owns the codebase invariants, live-code divergences from the initial design doc,
run procedures, and experimental findings for `~/work/next-connectionism`. Start
with the checkout's own `DESIGN.md` and
`next_connectionism/prompt-principle.md`. Sibling pages are the idea page
[knowledge/research/next_connectionism.md](../research/next_connectionism.md)
and the shared pipeline guide [knowledge/codebases/survival.md](survival.md).
Chapter 1 is the setting, architecture invariants, and where live code diverged
from `DESIGN.md`; Chapter 2 is the procedure to verify, train, and evaluate;
Chapter 3 records what the Commit-0 experiments found.

---

## Chapter 1 — Invariants And Divergences From `DESIGN.md`

### Worktree and `survival-pipeline` wiring

**`~/work/next-connectionism` is a git worktree of `~/work/survival` on branch
`next-connectionism-v2`, polled automatically alongside `sqa-remote` by
`survival-pipeline/poller.py`.** Pushing a commit with `run_config.yml` (`mode:
next_connectionism`) to `origin/next-connectionism-v2` runs `main.py --out
runs/<sha>/out` in a local `tmux` session and syncs outputs to
`many-agent-result`. Model calls go through the vendored `survival/amply_llm/`
client (`LiteLLM:vertex_ai/claude-haiku-5-5?reasoning_effort=medium`,
`VERTEXAI_PROJECT=viscam-cloud`) and never appear in `amp list`
([knowledge/codebases/survival.md §Codex → amply](survival.md#codex--amply-this-workstation-cannot-run-codex)).

### Where live code diverged from `DESIGN.md`

**Live code in `next_connectionism/` supersedes `DESIGN.md` on five interfaces
that evolved after the initial spec.**

| Area | What `DESIGN.md` says | What live code actually does |
|---|---|---|
| Agent IDs & Input Toggle (`types.py`, `config.py`) | `agent_0 .. agent_{N-1}` with fixed `input` subset | When `enable_input_agents: true`, canonical IDs are `input-0..input-{K-1}` and `worker-0..worker-{N-K-1}`. When `enable_input_agents: false`, canonical IDs are `agent-0..agent-{N-1}`, no role prompt is applied, and all $N$ agents receive the task input and wake at Solve start |
| Personality System (`types.py`, `prompts.py`) | Homogeneous base `system_prompt` | When `enable_personality: true` (default), `sample_agent_personalities()` draws 3 uniform $p=0.5$ axes per agent (`social_agency`: `proactive`/`reactive`, `epistemic_style`: `intuitive`/`analytical`, `construal_level`: `concrete`/`abstract`) and injects `## Personality Profile` into `system_prompt` (persisted in `personality.json`) |
| `comm_mode` names (`config.py`) | `message`, `git`, `shared_workspace` | Canonical names are `message`, `email`, `none` (`normalize_comm_mode` maps `git` to `email` and `shared_workspace` to `none`) |
| Email notifications (`tools.py`, `infra/`) | `wake_agent(target_id)` only | Incoming emails are silent unless the agent calls `wake_agent(target_id)` or copies `/shared/infra/email_alarm.py` to `/private/<id>/email_alarm.py` (`on_arrival` or `interval` mode, saved in checkpoints) |
| Interactive Update & Feedback Agents (`runtime.py`, `trainer.py`) | `update_allow_interaction=True` is planned | Implemented: before Update, `compact_conversation_for_update()` compacts long Solve transcripts (`>6` turns), optional `feedback-0..feedback-{F-1}` agents (`enable_feedback_agents: true`) inspect `/shared/_step_report/` to write `feedback_report.md`, and `update_allow_interaction: true` runs multi-turn post-mortem communication before finalizing `AGENTS.md` |
| Multi-task bundles & online eval (`trainer.py`) | 1 Commit-0 repo per step, standalone eval only | `task_groups` / `tasks_per_step` run $K$ repos per step (`repos/<task_id>`, timeout $\ge 100\text{s} \times K$), and `online_eval_steps` pauses training in-loop to call `run_online_eval` |
| Multi-domain 6+3 suite (`suite_env.py`) | Commit-0 only | `commit0_env.py` routes `suite_train_6` / `suite_eval_3` and 9 individual benchmarks to `suite_env.py` (6 train: `enterpriseops_gym`, `appworld`, `bbeh_mini`, `ifbench`, `spreadsheetbench`, `swebench_pro`; 3 OOD eval: `arc_agi_2`, `terminal_bench_4`, `automationbench`) |

### Prompt and two-tier memory invariants

**Read `next_connectionism/prompt-principle.md` before editing `prompts.py`,
`types.py`, `commit0_env.py`, or `tools.py`, because the test suite enforces its
seven prompt rules.** `build_system_prompt()` must stay 100% dataset- and
benchmark-agnostic (zero references to Python, `pytest`, or Commit-0) and must
never duplicate tool signatures in prose. When `enable_input_agents: true`, only
`input` agents receive the task prompt at Solve start while `worker` agents
start `STOPPED`; when `enable_input_agents: false`, no role prompt is injected
and every agent receives the task prompt and starts `RUNNING` at Solve start.
Per-agent persistent memory (`/private/<id>/AGENTS.md`) is read-only (`0444`)
during Solve and writable (`0644`) during Update, while temporary Solve notes go
in `/private/<id>/scratch/` and are wiped after Update.

### Sandbox, anti-cheating, and atomic git push invariants

**Only the `main` branch of the local bare repo `/task/code.git` (or
`/task/<task_id>/code.git` in bundles) is graded, and agents are isolated from
both the reference solution and each other's working trees.**
- `commit0_env.py` exports `base_commit` to `base_tree` and deletes
  `upstream_clone` before Solve so `reference_commit` never exists on disk.
- `_sanitize_venv_editable_paths()` removes `__editable__*` hooks and
  `base_tree` lines from `.pth` files in `.cache/commit0_envs/<task_id>/venv`,
  replacing them with `commit0_cwd_path.pth` so `pytest` imports the agent's
  own repo rather than the cached `base_tree`.
- `bash` and `run_pytest` run inside `bwrap --unshare-all --unshare-net
  --die-with-parent`, and `kill_all_active_subprocesses()` kills all tracked
  process groups (`_ACTIVE_PGIDS`) on timeout before evaluation starts.
- Concurrent pushes to `origin/main` are serialized via `flock` on
  `task/locks/git_push.lock` with automatic `git pull --rebase` in both
  `sync_and_push_code` and the `task/.bin/git` wrapper.
- When Solve cuts off an agent mid-turn, `repair_agent_events_for_update()`
  inserts synthetic cancellation `ToolResultEvent`s for dangling `tool_calls` so
  Anthropic/Vertex does not reject the Update stage with HTTP 400.

---

## Chapter 2 — Procedure: Testing, Training, And Evaluation

### Verify locally before launching a run

**Always run the hermetic `pytest` suite and a `--prepare-only` preflight with
`~/miniforge3/bin/python3` before starting or pushing a multi-agent run.** The
system `python3` lacks `litellm` and `datasets`.

```bash
cd /usr/local/google/home/qiaos/work/next-connectionism
PYTHONPATH=. /usr/local/google/home/qiaos/miniforge3/bin/pytest tests/
scripts/launch_staged.sh \
  --config configs/suite_6train_3eval_haiku55_n100_k10.yml \
  --name preflight_smoke \
  --foreground -- --prepare-only
```

### Launch, resume, and evaluate via immutable stagedirs

**Always launch training and evaluation jobs through `scripts/launch_staged.sh`
rather than running `python main.py` directly inside `~/work/next-connectionism`,
because `trainer.py` and `evalparallel.py` spawn child processes across steps
that will read mutated code if the working tree changes mid-run.**

`scripts/launch_staged.sh` snapshots `next-connectionism` and `survival` into a
read-only (`chmod -R a-w`) stage directory under
`~/.cache/next_connectionism/stages/<run_name>_<ts>_<gitsha>/` (with
`.stage_ready`, `stage_meta.json`, `git_head.txt`, and `git_diff.patch`), creates
the paired logdir `~/.cache/next_connectionism/runs/<run_name>/` (with resolved
`config.frozen.yml`, `train.log`, `pid.txt`, `launch_info.json`,
`launch_command.sh`, and `stagedir` symlink), and executes `main.py` strictly
from `stagedir`.

```bash
cd /usr/local/google/home/qiaos/work/next-connectionism

# Launch a staged background training run (logs to ~/.cache/next_connectionism/runs/<name>/train.log):
scripts/launch_staged.sh \
  --config configs/suite_6train_3eval_sonnet55_n100_k10.yml \
  --name suite_6train_3eval_sonnet55_n100_k10_fb_seed42 \
  -- --seed 42

# Resume an interrupted training run in-place:
scripts/launch_staged.sh \
  --config configs/suite_6train_3eval_sonnet55_n100_k10.yml \
  --name suite_6train_3eval_sonnet55_n100_k10_fb_seed42 \
  -- --resume-training

# Evaluate a frozen checkpoint without running the Update stage:
scripts/launch_staged.sh \
  --config configs/suite_6train_3eval_sonnet55_n100_k10.yml \
  --name eval_step010_sonnet55 \
  -- --eval-only --load-checkpoint ~/.cache/next_connectionism/runs/suite_6train_3eval_sonnet55_n100_k10_fb_seed42/checkpoints/step_010
```

Checkpoints live under `<logdir>/checkpoints/{step_000, step_XXX, latest, best}`
and store `agents/<id>/AGENTS.md`, optional `email_alarm.py`, and
`checkpoint_state.json`. When `online_eval_steps` and `online_eval_task_groups`
are configured, `trainer.run()` pauses after those steps to evaluate the frozen
checkpoint and writes `<logdir>/online_eval/step_XXX/eval_summary.json`.

---

## Chapter 3 — What The Experiments Have Found

### Phase II ($N=50$ agents, 38 non-lite multi-task bundles)

**Training $N=50$ `claude-haiku-5-5` agents (5 `input`, 45 `worker`) over 10
steps of $K=3$ non-lite repositories lifts held-out 3-group macro pass rate from
4.31% at step 0 to 16.84% at step 7 ($3.91\times$).** Full tables live in
`~/work/next-connectionism-reports/n50_bundle_report.html` (and the full prompt
audit is in `~/work/next-connectionism-reports/prompts_report.html`).

| Checkpoint | Group 1 (ID $K=3$) | Group 2 (OOD $K=3$) | Group 3 (OOD $K=5$ scale-up) | Macro avg pass rate | Total tests passed |
|---|---|---|---|---|---|
| `step_000` (untrained $\theta_0$) | 3.55% (68/1781) | 9.20% (74/4465) | 0.16% (14/8313) | 4.31% | 156 (3/11 repos $>0$) |
| `step_003` (30% trained $\theta_3$) | 8.42% (206/2520) | 22.87% (551/5962) | 3.80% (430/9345) | 11.70% | 1,187 (7/11 repos $>0$) |
| `step_007` (70% trained $\theta_7$) | 8.39% (228/2671) | 37.80% (296/4481) | 4.32% (409/8986) | 16.84% | 933 (8/11 repos $>0$) |
| `step_010` (100% trained $\theta_{10}$) | 4.43% (163/2546) | 19.32% (335/6412) | 4.53% (429/8885) | 9.43% | 927 (8/11 repos $>0$) |

### Late-stage prompt bloat and early stopping

**Accumulating too many prescriptive rules in `AGENTS.md` by step 10 causes
over-regularization on medium repositories, analogous to overfitting in classic
neural networks.** While the hardest $K=5$ scale-up group continues improving
through step 10 ($0.16\% \to 4.53\%$, $28.3\times$ more passed tests), macro
average peaks at step 7 (`16.84%`) with 19.1% lower token usage than step 0.
