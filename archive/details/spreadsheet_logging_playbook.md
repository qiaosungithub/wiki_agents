# Spreadsheet Logging Playbook

This is the from-scratch guide for logging VLM experiment results into the
shared spreadsheet. Use it when the user gives a WandB run, a tmux window id, a
job id, or an `output.log` path and asks to record results.

## Default Target

- Spreadsheet:
  `https://docs.google.com/spreadsheets/d/1FlcygQbGBTqHLJeiKdwxS0nP41SPMJrtX-kCJq8d7SQ/edit?gid=1739404389#gid=1739404389`
- Default worksheet:
  `PaliGemma-baseline-cleaned-20260608`, gid `1739404389`.
- Legacy worksheet, do not use by default:
  `PaliGemma-baseline`, gid `1146448969`.

Use the cleaned worksheet unless the user explicitly names another tab.

## Required Reading

Before logging:

1. Read `/kmh-nfs-ssd-us-mount/code/qiao/work/AGENTS.md`.
2. Read `wiki_agents/AGENTS.md`.
3. Read `wiki_agents/spreadsheet_logging.md`.
4. Read `wiki_agents/vlm_training.md`.
5. Read `wiki_agents/vlm_data.md` or `wiki_agents/vlm_checkpointing.md` if the
   task touches dataset locality, eval reruns, or checkpoint provenance.

Do not scan benchmark datasets or copy checkpoints across zones or regions for
spreadsheet logging. Use WandB summaries, run configs, tmux pane output, and
`output.log` text.

## Hard Stop Rule

Before writing anything, compare the run with the spreadsheet schema and nearby
rows. If any out-of-distribution behavior appears, stop and ask the user.

Stop on:

- A benchmark appears that the sheet does not already have a column for.
- An expected benchmark is missing, renamed, split differently, capped, or
  logged under a new key.
- The only available metric is not comparable, for example online eval instead
  of final eval, partial/sample eval instead of full eval, beam search instead
  of greedy, macro POPE instead of adversarial F1, or PCA-whitened KNN instead
  of raw KNN.
- Training or eval loss has an unexplained step reset, discontinuity, or large
  spike/drop.
- Multiple final evals disagree and the correct one is unclear.
- Existing spreadsheet cells already contain conflicting values.
- The requested action would require bulk data reads, benchmark JSON scans, or
  cross-region GCS movement.

WandB warnings caused by normal resume are not automatically a hard stop. Treat
them as acceptable only after checking the steps are monotonic or the resume
behavior is already understood from the logs.

## Interpreting User Inputs

### WandB Link

A link like
`https://wandb.ai/<entity>/<project>/runs/<run_id>` gives the project and run
id directly. Use the run id in the WandB API.

```python
import wandb

api = wandb.Api(timeout=60)
run = api.run("<entity>/<project>/<run_id>")
print(run.name, run.state, run.url)
print(dict(run.summary))
print(run.config)
```

Common projects:

- `sqa24-massachusetts-institute-of-technology/jax-llava`
- `sqa24-massachusetts-institute-of-technology/jax-llava_eval`
- `sqa24-massachusetts-institute-of-technology/paligemma-baseline`
- `sqa24-massachusetts-institute-of-technology/paligemma-baseline_eval`

### WandB Run Name

If the user gives a name such as `swift-durian-55`, search the expected project
first. If there are multiple matches, compare notes, config, timestamps, and
tmux/output logs before writing.

### Job identifier (infra id vs legacy window id)

A user-referenced run id is one of two kinds:

- **unified_infra job id** — an **8-char hex** (e.g. `a2056e02`) or a unique prefix.
  This is the current system. Resolve it with `infra info <id>` (status, `stage_dir`,
  `output.log`, `nodes`, `dead_runs`) and `infra logs <id>` / `cl <id>`. The
  `dead_runs` entries point at the `output.log` of each prior attempt, useful when a
  run resumed past a crash.
- **legacy xibo window id** — a **4-digit number** (e.g. `7620`), a tmux window in
  the old `sqa` session created by the TPU manager. Use this path only for historical
  runs that predate unified_infra.

If unsure which kind, an 8-char hex is an infra job; a bare 4-digit number is a
legacy window.

### Legacy Window ID

When the user says `window 7620` or just `7620` (4-digit), they mean a tmux
window in the `sqa` tmux session that was created by the old TPU manager.

Use:

```bash
tmux list-windows -a | rg '(^|:)7620:'
tmux capture-pane -t sqa:7620 -p -S -5000
```

The pane history often contains:

- The final WandB URL.
- `Job completed successfully` or the failure reason.
- The logdir and stagedir.
- Final eval log lines if WandB summary is incomplete.

If the tmux window no longer exists, look up the id in the TPU manager state if
the full state file is present. Some lightweight local files, such as
`tpu_manager/sqa.json`, are only status caches of running/finished window ids
and do not contain logdirs or WandB metadata.

```bash
find /kmh-nfs-ssd-us-mount/code/qiao/work/tpu_manager -name 'data.json' -print

jq '.. | objects | select((.windows_id? // empty | tostring)=="7620")' \
  /path/to/data.json
```

Also check `tpu_manager/queue.json`; completed queue entries can preserve
`wandb_notes`, TPU name, and finish time even when they do not store the final
WandB URL. Then inspect the job's `log_dir` and `output.log` if available. Do
not treat an absent tmux window as proof that the job never ran.

### Job ID

A user saying `job <id>` most often means a unified_infra job id (8-char hex);
resolve with `infra info <id>`. A 4-digit `job 7620` is a legacy xibo job whose
`windows_id` is `7620` — confirm in `tpu_manager/sqa.json` or the full TPU manager
state before relying on it. Either way, the spreadsheet logging target should be
tied back to the actual WandB run and logdir, not the id alone.

### `output.log`

If the user says to check `output.log`, search the relevant log file for WandB
links and final eval lines:

```bash
rg -n 'wandb.ai|Run summary|stage2_final|stage1_final|Job completed|Traceback|ERROR' \
  /path/to/output.log
```

Use log text only as a source of run identity or already-logged metrics. Do not
open generated benchmark result JSONs solely to compute missing metrics unless
the user explicitly approves and the access is same-region and safe.

## What To Pull From WandB

Always collect these facts before deciding where to write:

- Run identity: project, run id, run name, URL, state.
- Notes/tags: often contain the experiment purpose.
- Config:
  - Architecture and model family.
  - `txt_feature_layer`, `image_post_connector_scale`,
    `image_post_connector_transform`, image resolution, prompt causal settings.
  - Stage 1 and stage 2 dataset items and mix weights.
  - Freeze flags, especially `freeze_image_encoder`, `freeze_lm`,
    `freeze_lm_embed`, and `freeze_lm_late`.
  - Optimizer, learning rates, batch sizes, number of steps.
  - Eval tasks and beam size.
- Summary:
  - Prefer `*_stage2_final` for SFT/final rows.
  - Prefer `*_stage1_final` for pretrain rows.
  - For eval-only runs, use the final eval metrics from that eval run if it is
    clearly evaluating the intended checkpoint.
- History:
  - Check loss/step continuity.
  - Check stage transitions.
  - Use the final training `acc` and `loss` for Train acc/loss columns.

Example continuity check:

```python
import pandas as pd
import wandb

api = wandb.Api(timeout=60)
run = api.run("<entity>/<project>/<run_id>")
df = run.history(samples=2000)
loss_rows = df[df["loss"].notna()].copy()
steps = list(loss_rows["_step"])
step_decreases = [(a, b) for a, b in zip(steps, steps[1:]) if b < a]

stage_changes = []
if "curriculum_stage" in loss_rows:
    prev = object()
    for _, row in loss_rows.iterrows():
        stage = row.get("curriculum_stage")
        if pd.notna(stage) and stage != prev:
            stage_changes.append((int(row["_step"]), str(stage)))
            prev = stage

print(len(loss_rows), steps[:1], steps[-1:], step_decreases, stage_changes)
```

## Metric Columns

The current VLM table uses these columns:

| Column | Meaning | Preferred source |
|---|---|---|
| A | Setting | Human-readable experiment label |
| B | Note | Freeze status, eval caveats, RefCOCOg valid answer count |
| C | Dataset / mix | PaliGemma stage rows often use this |
| D | Details | LLaVA rows often use this for config details |
| E | CIDEr | Usually blank for current LLaVA/PaliGemma benchmark rows |
| F | MME-P / MME-S | `MME-P*_final` and `MME-S*_final`, rounded integers |
| G | VQAv2 | `vqav2_acc*_final` |
| H | TextVQA | `textvqa_acc*_final` |
| I | Train acc | final train `acc`; write as decimal so percent format works |
| J | Train loss | final train `loss` or `loss_vlm` |
| K | RefCOCOg | `refcocog_acc*_final` |
| L | MMBench | `mmbench_acc*_final` |
| M | POPE (adv F1) | `pope_adversarial_f1*_final`, not macro F1 |
| N | ImageNet KNN | raw/full KNN, not PCA-whitened KNN |
| O | VStar | greedy `vstar_acc*_final` |
| P | OCRBench | `ocrbench_acc*_final` |
| Q | MMVP | `mmvp_acc*_final` |
| R | CountBench | `countbenchqa_acc*_final` |
| S | VisWiz | greedy `vizwiz_acc*_final` |
| T | SEED-Bench | `seed_bench_acc*_final` |
| U | ScienceQA-IMG | `scienceqa_img_acc*_final` |
| V | GQA | `gqa_acc*_final` |
| W | WandB / run | Hyperlink formula or preserved run display text |

For VStar and VisWiz, beam-size-5 metrics may also be logged in WandB. Do not
put them in the main table unless the sheet row/block is explicitly for beam
search. Mention beam5 availability in the Note cell instead.

For RefCOCOg, also record the valid-answer count when it is already present in
WandB or output logs:

```text
RefCOCOg valid ans: 1383/7573 (18.26%).
```

If it is unavailable, write:

```text
RefCOCOg valid ans: n/a (not logged).
```

Do not open result JSONs only to compute this count.

## Choosing The Row

Do not append by default. Put new results near the closest comparable run.

Use this order:

1. If the user specified an exact row, use it after checking that the write will
   not overwrite conflicting data.
2. If an existing row already represents the run and cells are blank, fill that
   row.
3. If this is an eval-only rerun for a known training row, update or overwrite
   the corresponding row only when it is clearly the same experiment and the
   previous eval was wrong or incomplete.
4. For a pretrain plus SFT pair, use two adjacent rows:
   - pretrain/stage-1 row first,
   - SFT/stage-2 row second.
   If one WandB run runs both stages, still split the sheet into stage-1 and
   stage-2 rows.
5. For JAX LLaVA reproduction runs, place them in the LLaVA reproduction block,
   near rows whose architecture and ablation key match:
   - prompt-causal baseline near other prompt-causal rows,
   - late-fusion rows near the same `txt_feature_layer`,
   - scale or connector ablations next to the baseline they differ from,
   - freeze/LM ablations next to the corresponding full-LM row.
6. For PaliGemma recipe ablations, place them near rows with the same recipe
   family and only the intended changed key.

If the new run differs from nearby rows in more than the expected key, mention
that and stop before writing unless the user already acknowledged the
difference.

## Formatting And Trivial-Score Colors

The cleaned sheet has a rough trivial-score row near the top. Current baselines:

| Column | Rough trivial score |
|---|---|
| F MME-P / MME-S | `750 / 1050` |
| G VQAv2 | `0` |
| H TextVQA | `0` |
| K RefCOCOg | `0` |
| L MMBench | `25` |
| M POPE (adv F1) | `66.67` |
| N ImageNet KNN | `0.1` |
| O VStar | `25` |
| P OCRBench | `0` |
| Q MMVP | `50` |
| R CountBench | `10` |
| S VisWiz | `0` |
| T SEED-Bench | `25` |
| U ScienceQA-IMG | `20` |
| V GQA | `0` |

Mark cells red only when the logged value is below the rough trivial score. Do
not mark values equal to the trivial score. For the composite MME cell, mark it
red if either MME-P or MME-S is below its threshold.

Observed red background:

```python
red = {"red": 0.95686275, "green": 0.8, "blue": 0.8}
white = {"red": 1, "green": 1, "blue": 1}
```

After inserting a row, clear inherited metric backgrounds in `F:V`, then apply
red only to below-trivial cells. This avoids carrying old red cells into a new
row.

### Label-column red = encoder misconfig (separate from trivial-score red)

The label columns `A:D` are a **second, independent** red signal: they are red
**if and only if the run's encoder architecture is set wrong** — i.e. the run
intended encoder "426" (`enc_num_patch_sa_layers=4`, `enc_num_cross_attn_layers=2`,
`enc_num_token_sa_layers=6`) but actually ran "420"
(`enc_num_token_sa_layers=0`, the long-standing token-self-attention bug). The
`[wrong config]` blocks (e.g. rows 146–148) have `A:D` red across all stage rows;
a correctly-configured run must have `A:D` white. This is unrelated to the
trivial-score `F:V` metric reds.

Because `insert_rows(inherit_from_before=True)` copies the row above's format,
inserting below a `[wrong config]` block inherits its red `A:D`. So clear
**`A:E` as well as `F:V`** after inserting, then re-apply red to `A:D` **only if
this run's encoder is genuinely misconfigured**. Verify from the run config /
`output.log`: `enc_num_token_sa_layers=6` ⇒ correct 426 ⇒ keep `A:D` white.

## Writing The Sheet

Use the service account from `GOOGLE_APPLICATION_CREDENTIALS` when available.

```python
import os
import gspread

sid = "1FlcygQbGBTqHLJeiKdwxS0nP41SPMJrtX-kCJq8d7SQ"
gc = gspread.service_account(filename=os.environ["GOOGLE_APPLICATION_CREDENTIALS"])
sh = gc.open_by_key(sid)
ws = sh.worksheet("PaliGemma-baseline-cleaned-20260608")
```

Read nearby rows before writing:

```python
for row_num, row in enumerate(ws.get("A165:W175", value_render_option="FORMULA"), start=165):
    print(row_num, row)
```

Insert rows near a comparable block:

```python
rows = [
    [
        "setting label",
        "note",
        "",
        "details",
        "",
        "602 / 825",
        42.44,
        14.47,
        0.6193,
        1.75,
        0,
        2.15,
        66.67,
        "",
        36.65,
        15,
        50,
        14.46,
        2.96,
        23.19,
        35.25,
        41.37,
        '=HYPERLINK("https://wandb.ai/.../runs/<run_id>", "run-name | project - Weights & Biases")',
    ],
]

ws.insert_rows(rows, row=170, value_input_option="USER_ENTERED", inherit_from_before=True)
```

Format trivial-score cells:

```python
ws.format("F170:V170", {"backgroundColor": white})
for rng in ["F170", "L170", "T170"]:
    ws.format(rng, {"backgroundColor": red})
```

Read back both formulas and colors:

```python
print(ws.get("A170:W170", value_render_option="FORMULA"))

md = sh.fetch_sheet_metadata(
    params={"includeGridData": "true", "ranges": [f"{ws.title}!F170:V170"]}
)
```

In the final response, say which row was written, which run id/name it maps to,
and which cells were colored red.

## Common Cases

### User says `log 7620, 7609`

(4-digit numbers ⇒ legacy xibo window ids. For 8-char hex ids, resolve each with
`infra info <id>` / `infra logs <id>` instead of capturing a tmux pane.)

1. Treat `7620` and `7609` as tmux/xibo window ids.
2. Capture `sqa:7620` and `sqa:7609`.
3. Extract the WandB links from the pane tail.
4. Confirm each WandB run is finished.
5. Pull final metrics and config from WandB.
6. Check loss continuity and stage transition.
7. Find the comparable spreadsheet block.
8. Insert or update the rows.
9. Apply trivial-score colors.
10. Read back and report rows.

### User gives a pretrain and SFT run

Use adjacent rows. The pretrain row should contain stage-1/pretrain details and
stage-1 metrics. The SFT row should contain stage-2/final-eval details and
stage-2 metrics. If one WandB run performed both stages, still split it into
two spreadsheet rows.

### User says the old row is wrong

Do not guess. Re-read the old row, WandB config, output logs, and nearby rows.
If the intended correction is clear, update the row. If the correction changes
the interpretation of the experiment block or conflicts with existing notes,
stop and ask.

## Final Checklist

Before writing:

- Correct worksheet is selected.
- Run identity is unambiguous.
- Run is finished or user explicitly asked to log an incomplete run.
- Final metrics are comparable to the columns.
- Loss/steps are continuous or resume behavior is understood.
- Row placement is justified by nearby configs.
- Existing cells are blank or intentionally being corrected.
- No benchmark data or cross-region payload access is needed.

After writing:

- Read back `A:W` for changed rows.
- Verify formulas in the WandB column.
- Verify trivial-score red cells.
- Tell the user the row numbers, run names/ids, missing diagnostics such as
  `RefCOCOg valid ans: n/a`, and any non-blocking caveats.
