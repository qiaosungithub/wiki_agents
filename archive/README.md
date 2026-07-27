# Archive

Nothing under this directory is part of the default agent read path.

- `audits/` holds dated audit snapshots: scan counts, validation numbers, and
  status observations that back a rule in a core guide. They age; the guide's
  rule stays authoritative, and status must be re-verified live.
- `details/` preserves exact operational guides and one-off diagnostic examples
  that are too specific for core memory. It includes commands, thresholds,
  paths, incident ids, and pre-compression material.
- `legacy/` preserves verbatim snapshots of older repository-local agent memory.

Use these files only to recover provenance or troubleshoot a case that the core
guides cannot resolve. They describe multiple generations of the system and can
contradict current code. Never promote an archived command or state assumption
without verifying it against the current repository and live system.
