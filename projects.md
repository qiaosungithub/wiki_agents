# Project Map

Use this file to find the right source of truth. Read the checkout's own docs
and git state before editing it.

## Code Categories

Workspace repositories fall into two categories:
1. **Kaiming Group Code (Type 1)**: Code from the Kaiming group (e.g., `PaliGemma-baseline`, `jax_llava`, `beifen-Paligemma`, `beifen`). This machine is used solely to execute TPU tasks for these repositories.
2. **Google Internal Research Code (Type 2)**: Code natively for Google internal research (e.g., `project_one_ssl`, `one-benchmark-suite`, `nnflow_jax`).

*Note: Certain global constraints, such as the strict prohibition of cross-region data/checkpoint transfer, apply **only** to Type 1 (Kaiming Group) code.*

## Repositories

| Project family | Purpose | Core context |
|---|---|---|

| `jax_llava/` and its late-fusion snapshots | JAX LLaVA training, data, and evaluation | `vlm_training.md`, `vlm_data.md` |
| `PaliGemma-baseline/` | JIT/HSDP PaliGemma and PrefixMAE baseline | `vlm_training.md`, `vlm_data.md` |
| `beifen-Paligemma/` | Related pmap PaliGemma implementation and data pipeline | `vlm_training.md`, `vlm_data.md` |
| `beifen/` | Dataset upload and visual checks | `vlm_data.md` |
| `project_one_ssl/` | Project One v5 three-stream MAE/DAE baseline | Native `CLAUDE.md`, `docs/REPO_GUIDE.html`, and `docs/AGENT_CONTEXT.md` |
| `one-benchmark-suite/` | Benchmark registry, not a training framework | Native docs; archives only for old context |
| `nnflow_jax/` | JAX implementation of Generative Modeling Through Drifting | Native docs; archives only for old context |
| `readings/vision-related/tutorials/` | Paper deep-reading reports | `paper_reading.md` |
| `EqR/` and `EqR-jax/` | PyTorch and JAX codebase for Continuous space reasoning (Sudoku/Maze). | `projects.md` (see Boundary notes) |

## Project Boundaries That Are Easy To Miss

- `PaliGemma-baseline` and `beifen-Paligemma` share ideas but not execution
  semantics. Preserve the former's JIT/HSDP path and the latter's pmap path when
  porting changes.
- `one-benchmark-suite` owns benchmark definitions and CPU sanity checks. Do not
  turn it into a training framework.
- `project_one_ssl` has deliberate architectural constraints: the joint
  transformer starts from scratch, the frozen Gemma text stream is always
  present, Stream 1 and Stream 3 do not share mask tokens, and reconstruction
  loss covers all patches. Do not alter those choices as incidental cleanup.
  Its `CLAUDE.md` still names an older project-specific launch flow; verify the
  current scheduler instead of copying that launch section blindly.
- Snapshot and backup checkouts are not automatically the active source. Confirm
  the user's target path and branch before transferring a fix between them.
- `EqR-jax` uses XManager tier `PROD/BATCH` instead of xm_priority, and uses native XManager logging (historically named `wandb` in configs but does **not** require a WANDB_API_KEY). Path aliases are automatically mapped in `data_util.py` (e.g. `Maze-dynamic`, `Sudoku-aug1000`). Staging copies of the code are automatically pushed to `#$HOME/work/EqR-jax/` -> `google3/experimental/qiaos/eqr_jax_final_stages/run_<timestamp>` using the auto-generated `tpu queue` wrapper (`tpu_wrapper.sh`).
- For the `EqR-jax` maze dataloader: The `maze-dataset` library `grid_n=15` outputs $31 \times 31$ pixels, but EqR requires $30 \times 30$, so it trims/crops to the top-left $30 \times 30$ subgrid. The path length scaling is automatically done.
## Native Instructions

Repository-local instructions are authoritative for implementation details.
Generated run directories such as `.arc3-runs/` can also contain narrow local
`AGENTS.md` files; read the nearest one only when working inside that run.

The old exact memory snapshots are under `archive/legacy/`. They are useful for
recovering provenance, not for deciding how the current system works.

## Agent Tooling: Launching Jobs & Fetching logs

### HARD RULE: NEVER Use `xm launch` Directly
**CRITICAL RULE**: Agents must **NEVER** use `xmanager launch` or `xm launch` directly to submit jobs! You must **ALWAYS** use the wrapper command `tpu queue` (e.g. `source ~/work/tpu_cmd/tpu_wrapper.sh && tpu queue --tpu_type="..." --group="..."`). The wrapper handles staging, snapshotting, and registering job metadata into `~/.tpu_jobs.json` for tracking. Bypassing the wrapper breaks the user's tracking system.

Because the background agent environment lacks full LOAS identity for `xmanager.par tail_logs` and interactive TTY support, the correct way for the agent to inspect failed XManager job logs (e.g. for `EqR-jax`) is through the local `tpu_utils` tools. 
Agents should read and modify the script at `/google/src/cloud/<user>/xm_test/google3/experimental/users/<user>/tpu_utils/test_xmanager_api.py`.
By executing it via `blaze run experimental/users/<user>/tpu_utils:test_xmanager_api` (from the google3 workspace), the API can bypass the `xm tail_logs` blocks and fetch experiment `work_unit` details and dump the `status_message` directly.

## XManager Docker Packaging & TPU Topology
- **TPU v6e Topology**: In Borg, TPU v6e is referred to as `ghostlite_pod`. Similar to `v4` (`pufferfish`), Borg BCL evaluates `ghostlite_pod` strictly and requests a 2D array topology for core sizes rather than a scalar slice size (e.g. `4x4` instead of `16`). 
  - *Warning on 2x4 (v6e-8)*: While `2x4` is a formally valid physical slice for Ghostlite, many production cells/pools (like `deepmind-dynamic`) do not have capacity for such small chunks. Launching `v6e-8` (`2x4`) in these pools may cause Borg's Admission Controller to instantly reject it (XManager status `FAILED` without any logs or stack trace) rather than queuing it. Stick to larger slices like `v6e-16` (`4x4`), `v6e-32` (`4x8`), `v6e-64` (`8x8`) if immediate failure occurs.
- **TPU v4 Topology**: In Borg, TPU v4 is internally referred to as `pufferfish`, whereas `viperfish` is v5p. When requesting a `v4` slice larger than 8 cores, Borg requires a 3D topology string (e.g., `2x2x1` for 32 cores, `2x2x2` for 64 cores) rather than a scalar like `32`. Passing `32` directly triggers an `assertion failure in the job group ... pufferfish 32 is not supported` during BCL evaluation.
- **Python Container GCP Catch-22**: `xm.python_container` builds container images within Google Cloud Build. This requires the requested queue (pool) to have a mapped GCP project. While queues like `gdm-aux` (group 6) have mapping (`gdm-aux-xcloud`), PROD pools like `deepmind-dynamic` (group 1) generally do not. Therefore, using `group 1` with `xm.python_container` throws `No project set for pool_name: deepmind-dynamic`. Running native Borg code (`xm_abc.Borg`) via `bazel` (`package_mode="bazel"`) bypassing GCP entirely is the proper way to use PROD queues.
  - **Bazel Packaging for Research Py Code**: When shifting to `bazel` packaging for `xm_abc.Borg` execution in Google3, a `pytype_binary` macro is commonly used to bundle dependencies. By default, Bazel executes strict static type analysis (`Pyrefly`) and strict import checks (`PyStrictDepsCheck`) which break down on research repositories relying on external packages and implicit local imports (e.g. `import train` or `import utils.logging_util`).
  - **The Fix**: 
    1. **Preserve Code Freedom via sys.path injection**: Do NOT rewrite local imports to Google3 absolute paths (`experimental.qiaos.eqr_jax_final...`). Because Google3's `py_binary` strictly forbids the `imports` attribute, and standard python path injection via `PYTHONPATH` can be flaky under Borg runfiles execution, the definitive fix is to structurally modify the entry point file (`main.py`) to append its own execution directory to the path dynamically on launch: `sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))`. This allows standard Python imports (`import train`) to work flawlessly out-of-the-box in Google3 Borg runs without restricting your code freedom or polluting infra with hardcoded paths.
    1.b. **Skip Interactive Prompts**: To prevent XManager blocking on Research Hub attribution, set `attribution_urls=['rh/efforts/1910']` in `xm_abc.create_experiment()` to inject a dummy effort ID. Passing an empty list `[]` will still trigger the interactive prompt.
    2. Disable validations in `xm.bazel_binary` by injecting `bazel_args=["--define=PYTYPE=FALSE", "--norun_validations"]`.
    3. Ensure `testonly` pip packages (e.g. `//third_party/py/pytest`) are absent from the `deps` list, because Google3's MPM packaging aspect (`TemporalMpmAspect`) will cause skybuild analysis failures (contagion check) if a production target pulls in `testonly=1` rules without itself being flagged `testonly=True`.
    4. Move the `glob(["**/*.py", "**/*.yml", "**/*.yaml", "**/*.json"])` from the `srcs` attribute into the `data` attribute in the `pytype_binary`, keeping only `main.py` in `srcs`. This prevents the MPM aspect from flattening all subdirectories and failing on `Duplicate symlink '__init__.py'` during MPM `.runfiles` generation. It also ensures config files are correctly available for `open()` via Bazel runfiles.
    5. In `xm_launcher.py`, rewrite both the `--config` arg and the `config.sh` loading to point to the full Google3 runfiles absolute path `experimental/qiaos/eqr_jax_final/configs/load_config.py...` instead of just `configs/...` when `package_mode == 'bazel'`.

## Directory & Staging State
The `EqR-jax` repository acts as your unrestricted local workspace (located at `/usr/local/google/home/qiaos/work/EqR-jax`).
To bridge the gap between unrestricted Python development (`import train`) and Google3 Borg constraints, we heavily employ a **CitC Staging** mechanism integrated into `tpu queue`:

1. **Local Editing**: You edit files arbitrarily in `~/work/EqR-jax` (the `home code`) without any Bazel syntax restrictions.
2. **Auto-stagedir**: Launching jobs via `tpu queue` (`tpu_wrapper.sh`) will first auto-generate a unique timestamped staging copy in CitC for this job (e.g., `/google/src/cloud/<user>/EqR-jax/google3/experimental/qiaos/eqr_jax_final_stages/run_<timestamp>`).
3. **Trigger Launch**: It then copies `xm_launcher.py` into this unique `stagedir`, dynamically repoints the `TARGET_LABEL` in `config.sh` to this newly created staging folder, and runs the launch command directly from **inside** this `stagedir`.
4. This completely abolishes absolute symlinks errors and `import` path mismatches while retaining 100% snapshot reproducibility and tracking. All subsequent execution targets are packed via `xm_abc.Borg` bypassing GCP requirements in PROD queues.
