# Xibo Resume And Recovery

Use this guide when editing or diagnosing xibo/SQA resume, rerun, checkpoint
source selection, and stagedir recovery behavior. Read `xibo_monitor.md` for
active paths and locks, and `xibo_queue.md` for TPU selection rules shared by
queue and resume.

## Resume State And Invariants

- `sqa.json` is monitor local memory. `running` is an in-progress lock;
  `finished` means the window has already been handled by monitor.
- Active jobs are leaf jobs whose tmux windows still exist in the `sqa` session
  and have not been superseded by `extra_msgs.child`.
- Old `data.json` records can remain `error` or stale `running` after tmux
  windows disappear; those are history, not current work.
- Immediately diagnose any active `Error` leaf enough to classify it. No-card,
  TPU preempt, and deleted-card failures are operational churn; code, config,
  checkpoint, environment, and data-loader errors are abnormal.
- A resume/rerun attempt is consumed once external output shows a tmux job was
  created. The triggering failed window must then move to local `finished`, even
  if later sheet/alias bookkeeping prints `[FAIL]`.
- Do not add retry cooldowns to solve duplicate resumes. Desired behavior is to
  retry still-failed jobs on the next loop. The key invariant is that source
  windows are marked finished once a new child window is created.
- If an error window already has a recorded child, or its checkpoint source has a
  newer child than this window, treat it as stale and mark it handled locally.
- When checking whether a checkpoint source's child supersedes an error window,
  first walk the error window's `extra_msgs.father` chain. A child on the father
  chain is an ancestor path, not a competing newer child.

## Checkpoint Source Selection

- `find_saving_window.py` must not treat a bare `Saving checkpoint...` line as
  usable. A checkpoint is usable only after a later `saved to` line.
- The `saved to` line must be a model-checkpoint completion line such as
  `Checkpoint at step ... saved to ...` / `Checkpoint step ... saved to ...`.
  Do not count dataloader sidecar messages or paths under
  `_pending_dataloader_state` / `dataloader_state`; those are written before
  Orbax finishes and can exist beside a half checkpoint.
- If a latest `Saving` step is newer than the latest `saved to` step, remove that
  `checkpoint_<step>` candidate before returning the source.
- If stderr says `no complete checkpoint found anywhere in chain; reached root
  window N`, treat it as action `rerun` for root `N`.
- After walking a father chain, `find_saving_window.py` also scans same logical
  job using `(job_dir_id, spreadsheet_notes/job_tags)` and picks the highest
  complete checkpoint if newer than the father-chain checkpoint.
- The external backend should strip inherited resume-only overrides
  (`--config.load_from`, `--config.wandb_resume_id`, `--config.stage`) before
  composing resume/rerun commands.

## Resume/Rerun TPU Choice

- Training-phase checkpoint resume is exact-type: if action is `resume` and the
  job is still training, choose only the same TPU type as the original job,
  although another allowed zone/region with the same type is okay.
- Pretrain-phase checkpoint resume is stricter: if the job is still in stage-1
  pretrain / laion-aes pretrain, choose only the same zone and same TPU type.
  This avoids exact dataloader-state hydration across buckets whose shard
  contents may not be byte-identical across zones.
- Do not classify pretrain phase from notes alone. Two-stage job notes often
  mention `[laion-aes pretrain]` even during SFT; prefer the latest
  `curriculum_stage=` or `[stageN...] Starting ... phase` marker in
  `output.log`.
- Eval-phase resume is topology-flexible. If the failed/root job is `eval_only`
  or the log shows final eval has started, monitor may resume/rerun on another
  type or larger TPU, still respecting allowed zones and hard constraints.
- `laion-400m` overrides normal cross-region fallback and even old-card
  `resume_next_round` reuse: non-`asia-northeast1-b` TPUs are treated as
  unusable for that job.
- Because eval-phase work may be launched or resumed in a different allowed
  region, do not queue manual `eval_only` / just-final-eval jobs until the source
  final `checkpoint_<step>` has been copied to all allowed regions
  (`us-central1`, `us-east5`, `asia-northeast1-b`) with `tpu cc` or the current
  checkpoint-copy helper. Otherwise the eval run can either fail to find the
  checkpoint in the target zone or accidentally depend on cross-region reads.
- Checkpoint-free training `rerun` may choose a new type by exact cost class.
  `--same-type-only` forces checkpoint-free reruns to keep original type.
- `resume_next_round` buffer resumes must run the remote occupancy probe before
  directly reusing the old TPU. If old TPU is remotely busy, remove the buffer
  entry and fall back to normal different-card selection.
- If `tou` omits a TPU whose GCP state is `DELETING`, classify it as
  deleted/missing, not ambiguous. Deleted-card fallback should proceed.

## Resume-Needed Error Markers

Treat these as resume-needed infra or startup failures rather than permanent code
bugs when consistent with logs/state:

- `Retrying: SSH command error`
- `Unable to initialize backend 'tpu': ABORTED`
- `Fatal Python error: Aborted`
- `JAX distributed service detected fatal errors`
- `CoordinationService/Heartbeat` with `DEADLINE_EXCEEDED`
- `python: can't open file '/home/sqa/main.py'`
- `cp: cannot stat ... staging/sqa`
- `ModuleNotFoundError: No module named 'jax'`

For random JAX aborts, `tou` may still report the old TPU busy under `sqa`
because dead workers have not cleared. If busy users are only current user and
`data.json` plus tmux show no other active window, monitor may resume directly on
the old TPU.

## Implementation Pitfalls From Sandbox Notes

- `tmux display-message -p '#S:#I'` can report the active window, not the
  intended current pane's window. Use the pane id target:
  `pane_id=$TMUX_PANE; tmux display-message -p -t "$pane_id" '#S:#I'`.
- A function that acquires a lock must not exit while still holding that lock,
  or monitor/queue code can deadlock.
- Resume work should happen in the staged directory because the source checkout
  may have changed after the original job launched.
- For complex command argument passing, prefer positional arguments when that is
  what the existing xibo scripts expect.
- JSON and log parsing must be strict about type and case: `"3" != 3` and
  `"PREEMPTED" != "preempted"`.
- In f-strings, avoid using the same quote character inside expression braces as
  the surrounding string.
- `KeyboardInterrupt` is not caught by `except Exception`.
- `gcloud` can reconnect automatically. For SSH commands that should not keep a
  tmux pane alive, add `--ssh-flag="-n"`. When killing remote processes, also
  kill the parent if it restarts children.
- A remote crash may fail before writing useful text to `output.log`; absence of
  log output is not proof that the command never started.

## Stagedir Recovery Incidents

- `resume_rerun_job()` launches from the parent job's recorded `stage_dir`, not
  from `job_dir`. If old stagedirs have been cleaned, xibo can create a new tmux
  window that only fails with `cd: ... No such file or directory` and never
  starts remote training.
- Recovery pattern: identify the latest complete checkpoint from the parent
  `log_dir`, build a fresh recovery checkout with the original printed
  `FLAGS.config` when the source dir is gone, update the missing `working_dir`
  entry under the data lock, launch
  `tpu run ... --config.load_from=<parent_log_dir> --config.wandb_resume_id=<id>`,
  then mark the empty failed window as `resumed` with
  `extra_msgs.child=<new_window>`.
- Window 7706 on 2026-06-15 was this exact case. Window 7707 first recreated the
  job but was killed because it used code before the dataloader-startup probe
  refinement; window 7708 became the active recovery for W&B run `wmiengke`,
  restored exact dataloader state and model state from `checkpoint_177000` in the
  same `us-east5` bucket, and resumed stage-2 training. W&B may warn about
  non-monotonic steps if the previous run had advanced beyond the latest complete
  checkpoint; that is expected replay, not a failed restore.
- If the failed child never staged, it has `log_dir=None` and `stage_dir=None`.
  Do not resume that child directly; xibo resume requires a `log_dir` and will
  assert. Restore the parent chain leaf instead: set the parent's `stage_dir`
  and `job_dir` to the recovery checkout, set its status back to `error`, remove
  `extra_msgs.child`, and remove the parent window from local
  `tpu_manager/<user>.json.finished` under the local lock. Mark the empty child
  as `missing stagedir; superseded by manual recovery` and close the useless
  tmux window.
- Window 7715 on 2026-06-16 was this case: worker resumed 7697 and reported
  success after only creating tmux window 7715, but 7715 immediately failed
  `cd /kmh-nfs-ssd-us-mount/staging/sqa/260615142752-rr5xhy--code` and never ran
  `staging.sh`. The fix was to create
  `/kmh-nfs-ssd-us-mount/code/qiao/work/recover_7715_lxe04lfw` from current
  `beifen-Paligemma`, write 7697's printed `FLAGS.config` to
  `configs/remote_run_config.yml`, point xibo dir `34` and window 7697 at that
  recovery checkout, and let monitor retry 7697 from its latest complete
  checkpoint (`checkpoint_75000` in the 7697 logdir).
- Follow-up forensic check: xibo resume/run code does not delete stagedirs; it
  only records jobs and sends `cd <stage_dir>; source staging.sh ...` to tmux.
  On 2026-06-16 `/staging/sqa` had no `260614*` dirs and only `260615*` dirs
  after about 19:01 UTC, so the missing `260615142752-rr5xhy--code` was part of
  a broader staging cleanup/removal, not an isolated xibo resume bug. There was
  no matching `rm` in saved shell history, and NFS has no deletion audit here.
  Treat `/kmh-nfs-ssd-us-mount/staging/sqa` as non-durable: cleanup tools must
  skip every `job_dir`/`stage_dir` still referenced by active/resumable xibo
  jobs or by the local monitor state.

## Duplicate Window Incident

On 2026-05-14, repeated queue/resume windows were caused by success
misclassification: external `tpu run`/`resume` created a tmux window, then later
printed `[FAIL] get_zone_pre...` or sheet/alias bookkeeping errors. Correct
handling is based on creation signals such as `Successfully created job in tmux
window` or `run/resume/rerun job ... with new windows id N`; once seen, mark the
source/queue item consumed.
