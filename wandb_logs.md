# Reading WandB Logs from an Agent

Agents can programmatically access the console logs (stdout/stderr) of a WandB run to analyze failures, debug prints, or extract specific output from past runs.

## Method: Reading raw text logs

You can download or stream the raw `.log` file associated with any run using the `wandb` API.

```python
import wandb

def read_wandb_logs(entity: str, project: str, run_id: str):
    api = wandb.Api()
    run_path = f"{entity}/{project}/{run_id}"
    run = api.run(run_path)
    
    # The default log file uploaded by WandB
    log_file = run.file("output.log")
    
    # Download the file to a temporary location
    log_file.download(replace=True, root="/tmp/wandb_downloads")
    
    # Read the text contents
    with open(f"/tmp/wandb_downloads/output.log", "r") as f:
        logs = f.read()
    
    return logs
```

## Note on Offline Logs
If the run was executed in a VM where standard output was redirected to local files (e.g., inside /tmp/eqr_log...), WandB still intercepts and uploads the stdout/stderr buffer to the cloud dynamically. The agent does not need VM access as long as the run was initialized online.

## WandB to XManager Wrapping
For projects running natively on Google3/Borg (like EqR_jax), we have fully wrapped the WandB usage with a dummy proxy (`utils/dummy_wandb.py`). 
- **Metrics logging**: Calls to `wandb.log()` are transparently routed to `tf.summary.scalar` (TensorBoard), mapping neatly to XManager's `workdir` output so the metrics populate inside the XManager UI directly.
- **Run Resuming**: The concept of `wandb_resume_id` is replaced by XManager's `experiment_id` via the `--resume_xid` flag. This correctly mounts the workdir to the existing GCS bucket path, seamlessly appending to the previous TensorBoard charts.
- **Metadata**: Attributes like `wandb.notes` or run names are still captured but they are baked out to the `all_config.yaml` and `extra.json` inside the bucket rather than going to wandb servers.

