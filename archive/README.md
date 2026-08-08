# Archive

Not part of the default read path. Use it to recover provenance or to
troubleshoot a case the core guides cannot resolve — never to learn how the
system works now. These files span several generations and can contradict
current code; verify anything before acting on it.

| Directory | Holds |
|---|---|
| `audits/` | Dated investigations backing a rule in a core guide: scan counts, validation numbers, root causes. The guide's rule stays authoritative; re-verify status live. |
| `evidence/` | Findings from checkouts that were deleted. See its README. |
| `legacy/` | Verbatim snapshots of older repository-local agent memory, from before centralization. |

Git history is the real archive. Prefer deleting a stale file here over keeping
it: `git log --diff-filter=D --name-only` finds anything removed.
