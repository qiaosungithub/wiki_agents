# Chart Links And Reading A Job's Curves

Supporting reference for the result-logging skill ([SKILL.md](../SKILL.md)):
which chart URL a row carries, how to read a job's curves back from the
workstation, why only a work unit can write a datatable, and the provenance a
chart link does not carry. The W&B link column is [result-logging skill §The W&B Link Column](../SKILL.md#the-wb-link-column).

## Chart Links

A cluster job has no external tracker run, so "the chart" is a different URL per
backend. Resolve the one the job wrote; a URL rendering an empty page is worse
than no link.

| Link | Shows |
|---|---|
| `http://flatboard/xid/<XID>` | the metric curves; this is the link to log |
| `http://datatable/xid/<XID>/data` | the raw scalar table behind them |
| `http://xids/<XID>` | the experiment page (status, work units, config) |

**An empty page means no data was written, not a broken link.** The writer
announces itself on rank 0 at startup. A "could not start" or "log-only" warning
means the curves do not exist. Opting in to the table writer must be explicit,
since the default writes nothing and no error. A short `eval_only` job may never
reach the flush threshold, so its durable evidence is the metrics files under the
checkpoint bucket. Log that path too. Wiring: [knowledge/codebases/eqr-jax.md §Experiment tracking: the logging surface](../../../../knowledge/codebases/eqr-jax.md#experiment-tracking-the-logging-surface).

### Reading The Curves From The Workstation

**The workstation CAN read a job's curves. What it cannot do is call the
datatable service through its Stubby client, so a report must never say "the
workstation cannot read the datatable"; it says which of the three routes below
was tried and what came back.** Every route here was performed, not inferred;
re-perform route 3 against any finished XID before relying on it, because its
failure is a service state, not a rule.

| Route | Do | Gives | State |
|---|---|---|---|
| 1. The job's own bucket, first | torch lines: `fileutil cat <bucket>/sanity/<XID>_<WID>_att<N>_rank0.jsonl`. `EqR-torch-maze128` writes a `train_metrics` record per log interval (every `train/*` column, `samples_per_second` included), `eval_done` / `final_eval_done` carry the eval keys with values, `model_built` carries `tf32` and the matmul precision in force. Other torch lines built on the same `infra/beacon.py` have the lifecycle and eval records but not the train rows: port the one `beacon.emit(..., "train_metrics", ...)` call from `borg_trainer.py`. JAX lines: `fileutil cat <bucket>/logs/rank_<n>_attempt<k>.log` (which rank and which attempt hold the final curve: [eqr-jax-runs skill §Harvesting Final Train Metrics](../../eqr-jax-runs/SKILL.md#harvesting-final-train-metrics)); `~/work/xid2wandb/` parses those logs (`xid2wandb <XID> --dry-run` prints every row it recovered). | exact numbers at every logged step | works, no service in the loop |
| 2. The rendered page | `/google/bin/releases/gemini-agents-gbrowser/gbrowser --corp screenshot "http://flatboard/xid/<XID>" out.png`, then view the PNG. `--corp` is the persistent Chrome profile carrying corp auth; a login page in the PNG means `gbrowser login` once from a real terminal. The page auto-creates a dashboard whose plot 0 is `train/lm_loss`; `?activePlot=N` selects another. | the curve as a picture, data-freshness stamp included | works |
| 3. The numeric reader (Stubby) | `/google/bin/releases/gemini-agents-flatboard/flatboard_tool read_data --query=/datatable/xid/<XID>/data --limit=500 [--json --columns=step,train/lm_loss]`; `get_url --xid=<XID>` lists its dashboards. | the table as rows | the credential mints, then `Flatfish RPC failed ... /DataService.ReadTableData ... DEADLINE_EXCEEDED` on every table. This is the Stubby path a restricted LOAS cannot open; use route 4 instead of raising the deadline. |
| 4. The numeric reader (SSO, WORKS) | `ffhttp.py` in `experimental/users/qiaos/fbread/` (also vendored in `~/work/wandb-upload-daemon/`). Replays the Flatboard web UI's own HTTP call to `https://flatfish.corp.googleapis.com` via `gosso` — no Stubby, no LOAS. `python3 ffhttp.py --address=/datatable/xid/<XID>/data --columns=step,train/loss --n=0 --subset_mode=none`; or import it: `get_columns(addr)` lists every column, `read_table(addr, cols)` returns row dicts. | the table as rows, all columns | **works, including from a non-interactive (cron/tmux) shell** — verified 2026-09-12 reading real curves off a finished job. This is what the wandb-upload daemon uses. |

`gbrowser --corp text` and `html` return only the app shell: flatboard and the
datatable viewer are JS applications that fetch their data after load, so
route 2 is a screenshot, never a scrape. `xmanager` sees status, not scalars.

### Why Only A Work Unit Can Write One

Writing a datatable requires a Borg credential; a workstation cannot. The table
lives at `owner=…deepmind-jobs realm=… type=PROD`, and a workstation LOAS is a
*restricted* credential: `DatatableService.CreateTable` / `Read` through the
LOAS client both return `PERMISSION_DENIED` (`go/loas-restricted-credentials`),
as do `analog` and `xmanager tail_logs`. That is a statement about that client,
not about the curves ([§Reading The Curves From The Workstation](#reading-the-curves-from-the-workstation)). A metric
reaches a table only from inside a work unit, which mints a real prod
credential; `blaze run` on the workstation fails at table creation and cannot
verify the write either. So a job drops its own evidence where `fileutil`
reaches (route 1), and its log line `writing to http://flatboard/xid/<XID>` is
the proof that the table exists.

A finished run's empty chart can be backfilled from its text log. Such a run
predates the datatable writer but still has every logged scalar in its
`_boot_log` stream on CNS. A tiny CPU replay job (parse the rank-0 log, re-emit
via the same writer, keyed by the *new* job's XID) reconstructs the curves. The
source XID's table cannot be written once its work unit ends, so the row points
at the replay XID. Run it as a g9 PROD CPU controller
(`--tpu_type=cpu=N --group=9 --tier=PROD --skip-preflight --cell=<in-metro>`).
The g8 shared CPU pool routinely sits unscheduled: experiment `RUNNING`, work
unit never executes, no heartbeat, no log. The PROD controller schedules in
~1 min (the CPU-only row of [job-submit skill §Tiers and CPU-only](../../job-submit/SKILL.md#tiers-and-cpu-only)).

### Provenance: what the chart link does not carry

**A chart link resolves to metrics only.** It cannot say which code produced
them, so a chart-link-only row cannot answer "which snapshot was this?" — the
question a reproduction table exists for. The launcher writes these to the job
registry (`~/.tpu_jobs.json`, keyed by job id); none reaches the chart or the
experiment page:

| Field | Why the chart cannot recover it |
|---|---|
| `stagedir` | The immutable source snapshot that was packaged. The home checkout has moved on, so this is the only pointer to the exact code. |
| `logdir` | The launch log: command, resolved flags, allocator verdict. |
| eval outputs | Per-point metrics files and the FULLY RESOLVED eval config, including arch merged from the checkpoint. Survive when the table service has nothing. |

```bash
python3 -c "import json; e=json.load(open('$HOME/.tpu_jobs.json'))['<XID>'];
print(e['stagedir'], e['logdir'], e['bucket_cp_path'], sep='\n')"
```

`tpu clear` archives rather than deletes, so an old id still resolves from the
legacy file. But that registry is one local file on one workstation: the second
reason to copy these fields into the sheet.
