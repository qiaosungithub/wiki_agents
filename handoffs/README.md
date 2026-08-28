# Handoff Docs — The One Canonical Location

**Every handoff doc lives here, named `<line-name>.md`, and nowhere else.**
`<line-name>` is the roster name in `~/work/.monitor_watch/runs.txt` — the same
string the run's title carries. One file per line, overwritten each generation.

## Why one place, and why in git

A survey on 2026-08-28 found **~200 handoff files across 130 directories**:
`~/work/`, `~/work/.monitor_watch/`, `~/work/.monitor_watch/handoff_bodies/`,
`~/`, per-project dirs, eleven `.amply/artifacts/<rid>/` dirs, and 37 identical
copies dragged into experiment snapshots by `rsync`. Three costs, all measured:

- **A successor cannot find its own doc.** It is handed a path by the monitor; if
  that path is wrong the doc is effectively lost, and the next generation
  re-derives everything.
- **Nothing outside git is recoverable.** `~/work/.monitor_watch/` is *not* a git
  repo, so a doc there is one `rm` from gone. This directory is versioned.
- **Copies drift.** Same filename, different content, no way to tell which is
  current — and the wrong one reads exactly as authoritative as the right one.

## The rule

| | |
|---|---|
| **Path** | `~/work/wiki_agents/handoffs/<line-name>.md` |
| **Naming** | roster name, no version suffix, no date (`maze128-v6.md`, not `HANDOFF_maze128_v6_DRAFT_final2.md`) |
| **Generations** | keep the **current** one only; git history holds the rest |
| **Monitor's own** | `monitor-v<N>.md`; keep the **latest two**, delete older |
| **Commit** | `git add` + commit as part of the handoff, before you stop the old worker |

**Do not leave a second copy in the line's project directory.** A file sitting in
a project root gets swept into every staging `rsync` — that is how one doc ended
up duplicated 37 times inside sealed experiment snapshots. If a line wants its
doc nearby, symlink it.

**Snapshots under `~/tmp_seals/` and `~/tmp_pkg/` are sealed experiment records.**
Copies of handoff docs inside them are part of that record — leave them alone.

## Writing one

Format and content rules live in `../monitoring.md` §Handoffs: the line writes
its own doc, direction before detail, every run-id / XID / cell / CNS path
spelled out, and each claim tagged 【实测】/【推断】/【转述】.
