# Handoff Docs Live In `~/work/.monitor_watch/handoff_bodies/`

**The canonical location is `~/work/.monitor_watch/handoff_bodies/`, named
`HANDOFF_<line_name>.md` (underscores).** This directory is kept only as a
pointer; do not add handoff docs here.

Set by the operator on 2026-08-29: *"只放 handoff_bodies, wiki_agents 里面请改正。"*
This reverses the earlier rule that lived in this file ("every handoff doc lives
here, and nowhere else"), which had been added after a survey found ~200 handoff
files scattered across 130 directories.

## What the earlier rule was protecting against — still true, now solved differently

| Risk | How it is handled under the current rule |
|---|---|
| A successor cannot find its own doc | One directory, one naming convention: `handoff_bodies/HANDOFF_<line_name>.md` |
| **`.monitor_watch/` is not a git repo — one `rm` and it is gone** | ★Still an exposure. Keep the monitor's own backups (`backup_pre_v<N>_*/`) and never `rm` this directory wholesale |
| Copies drift, and the wrong one reads as authoritative | ★Do not keep a second copy anywhere — not in `wiki_agents/handoffs/`, not in the line's project directory (a file in a project root gets swept into every staging `rsync`; that is how one doc ended up duplicated 37 times inside sealed snapshots). If a line wants its doc nearby, symlink it |

**Snapshots under `~/tmp_seals/` and `~/tmp_pkg/` are sealed experiment records.**
Copies of handoff docs inside them are part of that record — leave them alone.

## Writing one

Format and content rules live in `../monitoring.md` §Handoffs: the line writes
its own doc, direction before detail, every run-id / XID / cell / CNS path
spelled out, and each claim tagged 【实测】/【推断】/【转述】.
