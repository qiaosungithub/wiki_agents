# Archive

Not part of the default read path. Use it to recover provenance, or to
troubleshoot a case the core guides cannot resolve; never to learn how the
system works now.

**These files span several generations of the system and can contradict current
code, so verify an archived command or state assumption against the current
repository and live system before using it.**

| Directory | Holds |
|---|---|
| `audits/` | Dated audit snapshots backing a rule in a core guide: scan counts, validation numbers, status observations. The guide's rule stays authoritative and status must be re-verified live. Delete a snapshot once it is too old to be evidence. |
| `details/` | The operational guides as they stood before the 2026-07-13 core-memory compression: exact commands, thresholds, paths, incident ids, and the user's then-uncommitted additions. |
| `legacy/` | Verbatim snapshots of older repository-local agent memory. |

Git history is also an archive: `git log --diff-filter=D --name-only` lists
removed files, so a stale page can be deleted rather than parked here.
