# Local Agent CLIs

Read this before changing how an agent CLI is launched or managed here. The
`agent-island` checkout and the live `~/.bashrc` are authoritative for current
wiring; the agent web app is [knowledge/codebases/agent-web.md](agent-web.md). All of this runs on
`sqa-large.c.googlers.com`; the migration from `sqa`, the re-sync recipe, and
what still runs where are in [knowledge/environment/workstation.md](../environment/workstation.md). The amply gateway URL is in
`~/.amply/dashboard_url` (the port changes per start).

Chapter 1 is the CLIs you type and how a named session starts. Chapter 2 is the
local database behind the amply gateway. The runbook for the gateway and its
local database is
[amply-operations skill §Chapter 1 — Operating The Amply Service](../../harness/skills/amply-operations/SKILL.md#chapter-1--operating-the-amply-service),
and the classic ways a run only looks dead are
[amply-operations skill §Chapter 2 — Classic Bugs: A Run That Only Looks Dead](../../harness/skills/amply-operations/SKILL.md#chapter-2--classic-bugs-a-run-that-only-looks-dead).

---

## Chapter 1 — The Agent CLIs And How A Session Starts

### `clod`, And The Jail It Runs In

**A command named `claude` is blocked by this host's `ai_agent_execution`
policy, so Claude Code is exposed as `clod`.** Only the name is refused. The
binary runs fine, so never conclude Claude Code is unavailable here. Same shape for `amp` (Amply chat), `gemini` (Jetski), `gpt` (Codex), `clod`
(Claude Code): each dispatches `new / list / search / id / resume / rename / clear`
to a session helper, else launches the agent.

`clod` runs Claude Code in a bubblewrap jail under `--permission-mode auto`.
Both layers are deliberate: the classifier catches bad tool calls, bwrap
contains what escapes it. Management subcommands only read/rewrite `~/.claude`,
outside the jail; `resume` re-enters it, so a resumed session gets a fresh
session's policy.

| Rule | Consequence of ignoring it |
|---|---|
| A wrapper imposing a permission policy must stop the session helper adding its own: `CLAUDE_LAUNCH_ARGS=""` drops the helper's `--dangerously-skip-permissions` | The two fight and the jail's auto mode is silently bypassed |
| The jail hides `/google/data`, `/google/bin`, `/google/src/head`, `/cns`, and other users' homes. `$HOME` and `/google/src/cloud/qiaos` are read-write, `/tmp` is a private tmpfs, the network is shared with the host | A task needing those runs outside the jail with `CLOD_NO_SANDBOX=1`; it is not a missing-file bug. `--unshare-pid` also hides host processes, tmux included, so the agent cannot signal them |
| `effortLevel` in `settings.json` stops at `xhigh`; only the CLI flag `--effort max` reaches the model, so `clod` passes it | `"max"` in settings is ignored and the session falls back to `high`. Claude Code accepts unknown settings values silently, so never read "it started fine" as evidence a setting took effect. The `effort` field of a `PreToolUse` hook's stdin payload reports the effective level |

### Named Startup: Registration, Readiness, And Native Names

The naming logic lives in `agent-island/claude-amply.py`, `codex-session-name.mjs`,
and `gemini-session-helper.sh`; `.bashrc` and `~/.local/bin/gpt` use them on each
new invocation. No gateway or database restart is needed for these CLI changes.

**`amp new NAME` applies `/annotate/title` as soon as the exact run ID is
registered, and registration is not readiness.** An independent read-only status
observer can detect a ready worker after a quiet or lost startup stream and
attach that same run, so never repeat run creation to repair the display.
Explicit worker failure still wins over a live observation. The configurable
default 600-second observation budget is not a hard deadline for every HTTP
operation.

**`gpt new NAME` creates one empty native thread, sets and reads back its native
name, then enters the TUI with that exact thread ID.** Updating only the SQLite
title or a sidecar while a new TUI is already running can lose to native
automatic naming on the first prompt; the native name survives actual first
input. Unsupported named-start options, including `--profile`, fail before
creating a thread, so use unnamed `gpt new` followed by the TUI's `/rename` for
those. Original unnamed new/resume behavior is preserved. Do not restore the
rejected global newest-thread or background title-watcher approaches.

**`gemini new [NAME]` passes `--title=NAME` with an empty prompt to `agentapi new-conversation` before attaching the CLI via a persistent background PTY daemon.** `agentapi` requires a prompt positional argument, so a blank prompt creates the conversation and binds the title without triggering an unsolicited turn. `find_agentapi()` resolves the executable across `AGENTAPI_BIN`, `PATH`, `~/.local/bin/agentapi`, `~/.gemini/jetski/bin/agentapi`, and on-demand extraction from the Jetski release SAR (`/google/bin/releases/jetski-devs/tools/internal/cli_internal`), preventing `[Errno 2]` in shells where `~/.gemini/jetski/bin` is not on `PATH`. It discovers `ANTIGRAVITY_LS_ADDRESS` automatically with socket liveness checks (filtering stale `/proc` environs and daemon files) and ensures `ANTIGRAVITY_PROJECT_ID=default-cli-project`. The local `.system_generated/custom_title.txt` and `conversation_summaries.db` are both updated before `launch_cli` starts `/google/bin/releases/jetski-devs/tools/cli` with `--model="Gemini 4 Argon (High)" --agent=argon` (Jetski's `ResolveModelFromFlag` matches the exact model label `"Gemini 4 Argon (High)"`; passing `"Gemini 4 Argon"` prints an unrecognized-model warning). Because `cli` embeds both its Language Server and BubbleTea TUI in one process and aborts the turn on `SIGHUP`, `_run_cli_with_tab_status` hosts `cli` inside a detached background PTY daemon (`~/.gemini/jetski/pty/`, `setsid` + Unix socket, auto-replying to `\x1b[6n` CPR queries while detached): an SSH disconnect only detaches the foreground client while the turn finishes in the background, `gemini resume <id|latest>` (`gr latest`) re-attaches to the live PTY with a 256 KiB replay buffer and `SIGWINCH` redraw, `gemini stop <id|latest>` terminates the background daemon, and detached idle daemons reap themselves after `GEMINI_DETACHED_IDLE_TTL` (default 6 h).

### `amp` Sends Operator Messages While The Agent Works

**A message typed at the `amp` spinner is sent immediately, mid-turn, not queued
until the turn ends.** `/chat/send` appends a `MessageEvent` and wakes the
session. The chatbot's `run()` loop re-reads its context every iteration. Within
seconds the message folds into the running turn at the next tool-call boundary,
surfacing as the `[STATUS]` NEW OPERATOR MESSAGE banner. A tool boundary is not
preemption: a long in-flight tool or the current LLM generation finishes first.
That is not a hang.

Slash commands are the one exception, still deferred to the idle prompt.
`/status`, `/help`, `/compact`, `/quit` print to the screen or mutate turn
state, unsafe while the hand-drawn spinner owns the bottom rows. See
`claude-amply.py` `_compose_submit_draft`: slash → `_queued_messages`, else
`_send_operator_message(..., begin_turn=False)`, so the in-flight turn's clock
is neither reset nor torn down on a send failure. The contract is pinned by
`agent-island/tests/test_queue.py`.

---

## Chapter 2 — The Amply Database

### The Amply Database Is A Local Spanner Test Universe

**Amply's database is `/span/test-universe/qiaos:amply`, served by a Spanner test
universe (`spanner::test::Env`) running on this workstation, not by `/span/tmp`.**
`/span/tmp/qiaos:amply` lost its write path (every commit hung, `span
getsafetime` deadline-missed, new workers sat forever at `[amply-startup 1/6]`)
and `/span/tmp` stopped allocating new databases, so the recovery does not depend
on Spanner at all. Old history is still in the old path and is copied over
opportunistically (below).

| Piece | Where | What it does |
|---|---|---|
| Universe host | `~/.amply/localdb/run_localdb.sh` → `bin/localdb` (unit `amply-localdb.service`, or tmux `amply-localdb`) | Starts the universe with CHUBBY_LOCAL, creates the database from `bin/amply_local.sdl.bundle`, restores `snapshots/`, then writes `ready` and `client_flags.txt` |
| Client flags | `~/.amply/localdb/client_flags.txt` | `--spanner_master_lockservice=localhost:<port> --default_ls_watcher=lockservice --lockservice_use_proxy=never`. Every amply process, and `span`, needs them to see the universe. **The port changes on every localdb start, so restart the gateway after localdb.** |
| Gateway | `~/.amply/bin/launch-ux-localdb.sh` (unit `amply-ux.service`, or tmux `amply-ux-local`) | Runs `bin/amply ux --spanner_db=... <flags>` from `~/work`; exports `AMPLY_WORKER_EXTRA_ARGS=<flags>` |
| Worker flags | local patch in `ux/server.py` (`_worker_extra_args`) | Appends `$AMPLY_WORKER_EXTRA_ARGS` to every spawned/resumed worker argv. Without it workers cannot reach the universe |
| Persistence | `~/.amply/localdb/snapshots/` (JSONL per run + `manifest.json`) | The universe is in-memory. localdb writes a delta every 5 min, a full re-dump every 6 h, and a final delta on SIGTERM. On start it publishes `ready` FIRST (gateway back in ~1 min) and restores history in the background, newest runs first, 4 threads (~300 rows/s; 120 runs ≈ 5 min). A crash loses at most 5 minutes; snapshots pause while a restore runs |
| History migration | `~/.amply/localdb/dump_loop.sh` (tmux `amply-dump-loop`) | Every 10 min: `dbtool dump` from the old database with `--schema_bundle` (its metadata path is dead, so the schema comes from the bundle), then `dbtool restore --skip_existing` into the universe. Progress: `dump_loop.log`, `snapshots/runs/*.jsonl` |
| Source | `//experimental/users/qiaos/amply_localdb` (`localdb.py`, `dbtool.py`, `amply_local.sdl`) | Rebuild with `blaze build`, then `~/.amply/localdb/refresh_bin.sh` copies binaries onto local disk (objfs GCs blaze outputs) and repoints their runfiles MANIFEST at that copy |

**Do not restore with the search indexes of the real schema.** `amply_local.sdl`
drops the `search_text_substr` n-gram tokenlist (3..12-grams over multi-MB event
JSON): with it, the single-process universe wrote ~15 rows/s and a 120-run
restore took hours with the gateway waiting. Full-text `SEARCH()` still works;
only `include_substring=True` searches fail on the local database.

**Restart order is automatic**: `amply-ux.service` is `PartOf=` +
`After=amply-localdb.service` (a crash-triggered auto-restart of localdb
restarts the gateway too), and `launch-ux-localdb.sh` additionally exits with 75
when `client_flags.txt` changes under it, so a gateway can never outlive the
universe it was pointed at. `amply_notify` keeps working on the local database
(it reaches the worker's control port, not Spanner).

**A gateway watchdog cannot fix a dead database, so it now checks both.** The
ops watchdog is `~/.tpu_bin/tpu_ops_watchdog.sh` (cron `*/2`, lock
`/tmp/tpu-ops-watchdog.lock`); it supervises the TPU pipeline + amply infra
(amply-localdb, gateway, tpu-check-daemon, dispatch worker, budget_enforcer),
logs in `~/.tpu_bin/logs/`. An earlier version probed only the gateway, so it
restarted the gateway repeatedly against a database that did not exist and
reported nothing about the real fault. It now also reads
`amply-localdb.service`'s `ActiveState` and, on `failed` or `inactive` only,
issues `reset-failed` + `start`. It deliberately does nothing when the unit is
`activating` (a restore runs for ~40 min after every start, and a restart throws
that work away), when the user bus is unreachable (cron has no
`XDG_RUNTIME_DIR`, and an unreadable state must not read as death), or when the
host is starved -- the same guard the gateway check uses.

**`amp new` takes 75 s on this database, 135 s when the corp-chubby timeout hits;
only the timeout is ours.** The 75 s: ~45 s importing the worker's Python
dependency graph out of the compressed par (55 s CPU; an uncompressed par saved
CPU but not wall time, so it was not adopted), 2 s to create the run, 13 s skill
index, 17 s until the first heartbeat makes the run "live". The extra 60 s comes
from the env's `--lockservice_use_proxy=never`: every client then tries the CORP
chubby cell directly (ACL lookups under `/ls/corp/...`), which is unreachable
from a workstation, and waits out `--lockservice_mount_timeout_secs`. Publishing
`--lockservice_direct_connection_regex=localhost.*` instead (local cell direct,
corp via the proxy) removes it with zero timeouts; localdb now writes that form,
and `~/.amply/localdb/apply_client_flags.sh` switches a running gateway (which
restarts it, killing live runs, so pick the moment).

Health in one line, a query by hand, the repair after a reboot, and the traps
met while building the universe are in
[Checking And Repairing The Amply Database](../../harness/skills/amply-operations/SKILL.md#checking-and-repairing-the-amply-database)
in the amply-operations skill.
