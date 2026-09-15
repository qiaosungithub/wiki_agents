# The Remote-Control Job Interface

A git-driven interface that lets a collaborator (lyy) launch cluster jobs by
**pushing commits**, and read their status back as a **git repo** — without ever
touching this workstation directly. Four checkouts under `~/work` make one
system; this page owns all four. Job mechanics live in `../jobs.md`; the `npu`
vs `tpu` registry split in `../infra/tpu_cli.md`.

## The Parts

| Checkout | Role | Runs as |
|---|---|---|
| `remote-control/` | INBOUND: the collaborator's GitHub repo. One commit == one run | GitHub `qiaosungithub/remote-control` |
| `remote-control-pipeline/` | The poller: turns each new commit into an `npu enqueue` | tmux `remote-control-poller` on sqa-large |
| `google-job-info/` | OUTBOUND: a git mirror of the `npu` board, one folder per job | GitHub `qiaosungithub/google-job-info` |
| `google-job-info-daemon/` | The generator: refreshes that mirror and pushes it | tmux `google-job-info` on sqa-large |
| `wandb-upload-daemon/` | REPORTING: when a job finishes, replays its Flatboard curves into W&B | tmux `wandb-upload` on sqa-large |

**Inbound, outbound, and reporting are independent halves.** The collaborator
pushes runs INTO `remote-control`, reads status OUT of `google-job-info`, and
reads curves OUT of Weights & Biases; no half knows about the others. The only
thing linking them is the `npu` registry (lyy's job board): the poller submits
into it, the generator mirrors it out, the wandb daemon watches it for finished
jobs. Reporting is covered in Chapter 3; the git-mirror status in the outbound
sections.

---

## Chapter 1 — How It Works (原理)

### Inbound: one commit is one run

**The `remote-control` repo root IS the code. A commit is a whole new tree plus
a `run_config.yml` at the root describing that run.** There is no separate "job
spec" directory: the tree at commit `<sha>` is exactly what gets packaged and
launched, and `run_config.yml` says how (compute shape, tier, config, launch
flags). The tree today is a parcae PyTorch training package (`main.py`,
`train.py`, `models/`, `configs/`), but the poller does not care what the code
is — it only reads `run_config.yml`.

### The poller, one tick

`remote-control-pipeline/poller.py` runs on a loop (`poller_loop.sh`, tmux,
every 120 s, single-instance via flock). Each tick:

1. `git fetch` the tracked clone in `repo/`.
2. List commits on the tracked branch (origin default), **oldest first,
   first-parent only**.
3. For each commit not yet in `state/processed.json`:
   - export `git archive <sha>` into an **immutable** `runs/<sha>/`;
   - parse `runs/<sha>/run_config.yml`;
   - dispatch on `mode` (only `launch_job` today);
   - `npu enqueue … --workdir=runs/<sha>/ …`, read back the `enqueued <id>:`
     line, and record the outcome.

**The poller only ENQUEUES; it does not build or submit.** The separate
`npu build-worker` (its own tmux) drains the queue minutes later and does the
real Borg submission. This is why the snapshot must be frozen (below).

### Why a frozen snapshot per commit

**`npu enqueue` only records a workdir; the build-worker rsyncs and builds it
later, so the workdir must not move.** If the poller pointed enqueue at a single
shared checkout, a second commit would rewrite the tree before the first job is
packaged, and the first job would build the wrong code. Exporting each commit
into an immutable `runs/<sha>/` and enqueuing `--workdir=runs/<sha>/` guarantees
a job packages the exact code of its own commit.

### `run_config.yml` → `npu enqueue` translation

`_build_enqueue_args` maps the yml to flags. The schema (see
`remote-control-pipeline/examples/run_config.yml` for the annotated copy):

| yml key | Required | Becomes | Notes |
|---|---|---|---|
| `mode` | yes | dispatch key | only `launch_job` today |
| `power` | yes | `--power=` | an `<arch>-<chips>` shape, e.g. `h100-8`, `v6e-16`. A chip count is not a size (`../tpu_reference.md`) |
| `archs` | yes | `--archs=` | list; give several so a preempted job can re-place |
| `metros` | recommended | `--metros=` | where the data lives; the write metro must be listed |
| `tier` | no (PROD) | `--tier=` | training must be PROD (`../AGENTS.md` Global Rules) |
| `config` | no | `config=` in `--launch` | forwarded verbatim; the launcher maps it to a config file |
| `exp_name` | no | `--job_name=` + `exp_name=` in `--launch` | base name; poller automatically appends `-<short-sha>` (defaults to `rc-<short-sha>`) to prevent queue collisions |
| `launch` | no | extra `--launch` k=v pairs | `true` → bare flag; `false`/`null` dropped; **no commas in a value** |
| `priority` | no | `--priority=` | **clamped to 0** unless `RC_ALLOW_PRIORITY=1` |
| `power_tolerance`, `max_price`, `topology_locked` | no | matching flags | advanced |

Each commit is recorded in `state/processed.json` with one of:

| Status | Meaning | Retried? |
|---|---|---|
| `DISPATCHED` | enqueue accepted it; `job_id` recorded | no |
| `FAILED_CONFIG` | bad/missing yml or unknown mode | never |
| `FAILED_DISPATCH` | enqueue invoked but refused/crashed | never |
| `SKIPPED_BASELINE` | pre-existed at first tick (see below) | never |

### Outbound: the status mirror

`google-job-info-daemon/daemon.sh` runs on a loop (tmux, every 900 s / 15 min).
Each tick: `generate.sh` sources the wrapper, runs `npu check -a -f` and
`tpu money`, strips ANSI into `npu_check.txt` / `tpu_money.txt`; then
`generate.py` fans the board out into `jobs/<xid>__<name>/{status.txt,
status.json}`; then git add / commit / push — **committing only if something
changed**.

**It mirrors the WHOLE `npu` board, not just remote-control jobs.** Every job in
lyy's registry becomes a folder. A remote-control run therefore appears here too,
under its `exp_name`, once the build-worker submits it — that is how the
collaborator watches a run they launched. A done job's files are written
byte-identical every tick (no per-file timestamp; the one refresh time lives in
`updated_at.txt`), so git only records jobs that actually changed.

---

## Chapter 2 — Using It (使用方法)

### The collaborator's side (launch a run)

1. Add or edit `run_config.yml` at the repo root, and commit the code you want
   to run alongside it.
2. `git push` to the tracked branch. That is the whole action: the push IS the
   launch.
3. Watch it in `google-job-info`: find `jobs/<xid>__<exp_name>/status.txt`, or
   read `npu_check.txt` / `index.md` at the repo root.

One commit fires exactly one run. To launch again, push another commit.

### The operator's side (run the pipeline)

Both halves run as resident tmux loops on `sqa-large`, restartable by hand:

```bash
# inbound poller
tmux new-session -d -s remote-control-poller \
    ~/work/remote-control-pipeline/poller_loop.sh

# outbound status daemon
tmux new-session -d -s google-job-info -c ~/work/google-job-info-daemon \
    'while true; do bash daemon.sh; echo "restart in 30s"; sleep 30; done'
```

The poller needs the `npu` shell function (its scripts source the wrapper) and a
live `npu build-worker` to actually submit. `run_poller.sh` is the cron variant
of one tick (`*/2` + flock), used instead of the tmux loop if you prefer cron.

### Test a commit without firing a job

```bash
cd ~/work/remote-control-pipeline
RC_DRY_RUN=1 RC_PROCESS_BACKLOG_ON_INIT=1 python3 poller.py
```

This does everything except invoke `npu`, printing the exact `npu enqueue`
command for each commit.

### The knobs (env vars)

Poller: `RC_REPO_URL`, `RC_BRANCH` (auto = origin default), `RC_SUBMIT_CMD`
(`npu`|`tpu`), `RC_DRY_RUN`, `RC_ALLOW_PRIORITY`, `RC_PROCESS_BACKLOG_ON_INIT`,
`RC_HOME`, `RC_POLL_INTERVAL`. Daemon: `GJI_REPO_DIR`, `GJI_INTERVAL`,
`GJI_BRANCH`; `generate.py` reads the registry from `NPU_JOBS_FILE`
(`~/lyy-work/.npu_jobs.json`).

---

## Chapter 3 — Curves To W&B (原理 + 使用)

**When a job finishes, its Flatboard curves are replayed into Weights & Biases**
by `wandb-upload-daemon/`. This half needs ZERO training-code change: it reads
the datatable every framework already writes, not a special log line.

### How the reporting daemon works

One tick (every 15 min, tmux `wandb-upload`):

1. Read the `npu` board (`~/lyy-work/.npu_jobs.json`).
2. For each job in a terminal state (`COMPLETED` / `TERMINAL_*`) not already
   handled: read its datatable `/datatable/xid/<XID>/data` — every `train/*`,
   `val/*` column, keyed by step.
3. Recover the launch **git_commit** (below), load that commit's frozen
   `runs/<sha>/run_config.yml`, and take its `wandb:` block.
4. Replay the rows into a W&B run (`run_id=xid-<XID>`, so a re-run UPDATES the
   same run — idempotent).

### Two facts that make it possible

**Reading the datatable from the workstation.** A workstation's restricted LOAS
cannot call the Flatfish DataService over Stubby (it hangs → `DEADLINE_EXCEEDED`).
But the Flatboard *web UI* reads it over UberProxy SSO, and `ffhttp.py` (vendored
in the daemon) replays exactly that HTTP call via `gosso` — works even from a
non-interactive cron/tmux shell. `get_columns()` discovers columns,
`read_table()` pulls rows. Full route table: `../research/result_logging.md`
§Reading The Curves From The Workstation (route 4).

**Recovering the commit from an xid.** A run's W&B destination lives in its
commit's `run_config.yml`, but the daemon only has an xid. The poller records
`git_commit=<full-sha>` as a launch param; the daemon reads it back with
`xmanager_tool get_experiment --xid=<XID> --include_fields=launch_command` and
`grep`s out the sha. `exp_name` stays human-readable — the sha travels as a
param, not in the name. (XManager stores launch params server-side, queryable by
xid; `read_config` / `--include_fields=parameter_configuration,user_command` are
the other queryable views.)

### The per-run `wandb:` block (collaborator writes this)

In a commit's `run_config.yml`, every key optional, all per-run:

```yaml
wandb:
  project: my-wandb-project   # default: remote-control
  name: my-first-remote-run   # default: exp_name, then xid-<XID>
  notes: "lr sweep arm A"      # default: exp_name
  tags: [parcae, smoke]
  # entity: some-other-team    # default: the operator's own entity
```

Set `project` to send different commits to different W&B projects. The daemon
uploads under the operator's entity/API key by default (operator + lyy share
most projects).

### Operator: run the reporting daemon

```bash
tmux new-session -d -s wandb-upload -c ~/work/wandb-upload-daemon \
  'while true; do python3 daemon.py --once >> logs/daemon.log 2>&1; sleep 900; done'
```

Manual controls: `python3 daemon.py --once --dry-run` (plan the whole board,
change nothing); `python3 daemon.py --xid=<XID>` (upload one job, ignoring
state — the test path). On first start it BASELINES every pre-existing terminal
job (records them as skipped, uploads none), so only jobs finishing *after* the
daemon starts are uploaded — historical jobs are not back-filled.

## Chapter 4 — Common Debug (常用 debug)

### First-run baselining is not a bug

**The first ever poller tick BASELINES all existing commits (`SKIPPED_BASELINE`)
and launches nothing.** Turning the daemon on does not fire the repo's history;
only commits pushed after that fire. Set `RC_PROCESS_BACKLOG_ON_INIT=1` on the
first tick if you actually want the backlog.

### A processed commit is never retried

**Once a commit is in `state/processed.json` it is never processed again, in any
status.** This is deliberate: a flaky re-read cannot double-submit. So a
`FAILED_CONFIG` / `FAILED_DISPATCH` commit stays failed. To fix a bad run, push
a NEW commit; do not expect the poller to pick the old one up again. Re-running
the identical tree means either a new (empty) commit, or carefully deleting that
sha's entry from `processed.json`.

### Inbound (poller) symptoms

| Symptom | Likely cause | Check / fix |
|---|---|---|
| A pushed commit never launches | poller loop not running | `tmux has-session -t remote-control-poller`; `tail logs/loop.log`; restart |
| Commit dispatched, but job never schedules | poller only enqueues; the build-worker submits | `tmux has-session -t npu-build-worker`; `npu check`; `npu queue-status` |
| Commit shows `FAILED_CONFIG` | missing/invalid `run_config.yml`, or unknown `mode` | read the `error` in `processed.json`; fix yml; push a NEW commit |
| Commit shows `FAILED_DISPATCH` | enqueue ran but was refused | `error` field + `logs/poller.log` tail; fix, push new commit |
| A `priority>0` request had no effect | clamped by default | set `RC_ALLOW_PRIORITY=1` only if you really mean to park the shared queue |
| Want to preview the exact command | dry run | `RC_DRY_RUN=1 … python3 poller.py` |

### Outbound (daemon) symptoms

| Symptom | Likely cause | Check / fix |
|---|---|---|
| `google-job-info` stops updating | daemon loop not running | `tmux has-session -t google-job-info`; `tail google-job-info-daemon/logs/daemon.log` |
| Tick logs "empty output; aborting" | `npu check` returned nothing | the tick keeps the last good snapshot on purpose; check the wrapper / registry |
| No new commit though jobs changed | nothing truly changed, or push failing | `git -C ~/work/google-job-info log -1`; daemon.log for push errors |
| Job folder missing for a run | not on the board yet, or pruned when it left | folders mirror the live board; a vanished xid is pruned by design |

### Affects both halves

| Symptom | Cause | Fix |
|---|---|---|
| Nothing updates after a reboot | tmux does not survive reboot, and there is no `@reboot` cron | re-create both tmux sessions by hand (Chapter 2) |
| `npu: command not found` when run by hand | the `npu` shell function only exists after sourcing the wrapper | `source ~/work/tpu_cmd/tpu_wrapper.sh` first |
| Confused which registry a job is in | `npu` = lyy's registry, `tpu` = sqa's; same CLI, different board | `../infra/tpu_cli.md`; the pipeline uses `npu` by default (`RC_SUBMIT_CMD`) |
