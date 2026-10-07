---
name: survival-operations
description: Launch a survival run (by pushing to the sqa-remote branch or by hand), run the survival-pipeline daemon, and debug a commit that never ran, a failed run, or a result that never synced.
---

# Operate The Survival sqa-remote Pipeline

Read [knowledge/codebases/survival.md](../../../knowledge/codebases/survival.md)
first for what a run is (the game, the blank-agent invariants, the codex to
amply adaptation, model selection, and the output contract) and how a commit
becomes a run (the poller, the run config, the result sync, and recorded
state). This skill owns launching runs, running the daemon, and common debug.

Chapter 1 is using it; Chapter 2 is common debug.

---

## Chapter 1 — Using It (使用方法与注意事项)

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

## Chapter 2 — Common Debug (常用 debug)

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
