# Reading CNS Fast Enough For A CLI

Read this before putting a `/cns/` read on the path of anything interactive (a
status table, a watch loop, a progress display). It is about LATENCY, not about
which cell to use -- `data_locality.md` owns placement.

All numbers below were measured from a workstation in metro `sq` against live
job logs in `yutulpz` (metro `tul`), 2026-07-31. Re-measure before trusting a
figure; the shape of the conclusions is what matters.

## The Cost Is Round Trips, Not Bytes

A small CNS read costs about the same as a large one. Reading 4 KB and reading
431 KB from the same file both landed around the same time, because the RPC
round trip dominates.

The three practical consequences:

- **Seeking to the tail is worth doing, but it is not a speedup.** At 1 MB,
  `seek(-16K, SEEK_END)` beat `read_bytes()[-16K:]` by only ~1.4x. Do it anyway:
  the naive form's cost grows with the file, so a run that logs for hours
  eventually pays for every byte it ever wrote.
- **Never put a per-file `stat()` inside a `sorted(key=...)`.** That forces the
  calls serial and is invisible in the source. This was the single biggest cost
  in `infra_check._log_tail`.
- **Fan out with a thread pool.** The CNS client releases the GIL, so this is
  real concurrency: 8 files went from 1.32s serial to 0.14s pooled (~9x).
  Reuse one module-level pool; building one per call costs more than the reads.

## Distance Is Not The Explanation

Cross-metro was NOT the driver. From a metro-`sq` workstation:

| Target | `fileutil ls` |
|---|---|
| `sq-d` (the LOCAL metro) | 6.60s |
| `nz-d` (remote) | 1.87s |

The local cell was three times SLOWER. Per-cell load and metadata-service
responsiveness dominate; physical distance is second-order. Do not diagnose a
slow read as a locality problem without measuring another cell.

## `fileutil` Is A ~1s Tax Before It Does Anything

| Measurement | Time |
|---|---|
| `fileutil help` (touches no network) | 1.05s |
| `fileutil ls /tmp/` (local dir) | 1.00s |
| one CNS tail read | 3.77s |
| four in ONE invocation | 6.30s |

So: ~1.05s of binary startup, ~1.9s more for first-connection setup, then only
~0.84s per additional file. Batch paths into a single invocation when you must
shell out -- `fileutil cat f1 f2 f3` is far cheaper than three calls.

## Prefer `epath` — But Only In A Long-Lived Process

`etils.epath` is the in-process client (the one orbax uses). Same work as the
table above:

| Scenario | `fileutil` | `epath` |
|---|---|---|
| first CNS op (client init) | — | 1.28s |
| single file tail | 3.77s | cold 1.3s / **hot 0.13s** |
| **4 files (one status refresh)** | **6.30s** | one-shot 4.4s / **hot 0.136s** |
| `stat()`, hot | — | 32ms |
| after 60s idle | pays 6.3s again | **still hot, 370ms** |

Two rules follow:

- **A one-shot binary gains almost nothing.** End to end a par binary is ~4.4s
  (1.74s par startup + 1.28s client init) against fileutil's 6.3s. Not worth a
  rewrite.
- **A process that stays up wins ~46x**, and the client does NOT go cold across
  a 60s idle gap, so a once-a-minute poller keeps paying the hot price.

If a loop is a bash script that re-execs a binary every round, it is a one-shot
caller no matter how long the loop runs. Put the read inside a program that is
already paying the startup cost, or make the loop itself a resident process.

## Two Traps That Fail Silently Or Late

- **pip-installed `etils` cannot see `/cns/` and does not say so.** The open
  source build strips the gfile backend (`# copybara:strip` in `gpath.py`), so
  `/cns/...` is treated as an ordinary POSIX path: `exists()` returns **False**,
  no exception. Only a Blaze target depending on `//third_party/py/etils/epath`
  has the real backend. A conda/pip interpreter will report every log as
  missing.
- **No file or RPC access before `InitGoogle()` finishes.** Touching CNS at
  module import time in a Blaze Python binary aborts the process with a stack
  trace pointing at `CheckInitGoogleIsDone()` (go/no_file_or_rpc_during_init).
  Do the work inside `app.run(main)`, never at module scope.

## Worked Example

`infra_check.py::_read_log_tail` / `_fetch_log_tails` is the reference
implementation: pooled `stat()` per rank, `seek()` to the tail, every job's tail
prefetched concurrently before the render loop, and a hard ceiling on the whole
phase so an unhealthy cell degrades the display instead of hanging it. Measured
1271ms -> 402ms across two live runs.

Always bound the wait. A tail is a nicety; a status table that blocks on it is a
regression.
