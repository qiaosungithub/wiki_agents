# Pre-Restructure Evidence

Verbatim copies of core guides as they stood at commit `b3ef8dd`, immediately
before the 2026-08-02 restructure. They are kept because the restructure
deliberately removed material that a core guide should not carry: source line
numbers, job ids, dated measurement tables, per-cell observations, and
bit-exact arithmetic.

Every **rule** in these files survives in the current guides. What is here and
not there is the supporting evidence. Consult a file only to answer "what was
the actual measurement / the exact code path", never to decide how the system
works today — several of these details are already stale by design.

| File | Superseded by |
|---|---|
| `xmanager_full_20260801.md` | `jobs.md`, `infra/quota_market.md`, `infra/tpu_cli.md`, `tpu_reference.md` |
| `data_locality_full_20260801.md` | `storage.md` |
| `cns_latency_measurements_20260731.md` | `storage.md` §Distributed Reads (holds the measured tables) |
| `spreadsheet_full_20260801.md` | `research/result_logging.md`, `projects/eqr_jax.md`, `projects/vlm_metrics.md` |
