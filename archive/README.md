# Archive

Nothing under this directory is part of the default agent read path.

- `audits/` holds dated audit snapshots: scan counts, validation numbers, and
  status observations that back a rule in a core guide. They age; the guide's
  rule stays authoritative, and status must be re-verified live.
- `evidence/` holds verbatim pre-restructure copies of core guides, kept for the
  measurements, source paths, and incident forensics that a core guide must not
  carry. Its own README maps each file to what replaced it.
- `legacy/` preserves verbatim snapshots of older repository-local agent memory.

Use these files only to recover provenance or troubleshoot a case that the core
guides cannot resolve. They describe multiple generations of the system and can
contradict current code. Never promote an archived command or state assumption
without verifying it against the current repository and live system.
