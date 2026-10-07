# Workspace Harness And Knowledge

This directory holds two distinct kinds of maintained content. Agents start at
[AGENTS.md](AGENTS.md); humans can browse the indexes below.

| Location | Purpose |
|---|---|
| [harness/](harness/README.md) | How agents should work: shared rules and task skills |
| [knowledge/](knowledge/README.md) | What is known about the user's codebases, environment and research |
| [archive/](archive/README.md) | Historical snapshots and supporting operational evidence |

```text
wiki_agents/
  AGENTS.md                 Agent bootstrap and task router
  harness/
    policy.md               Shared constraints and authorization
    engineering.md          Working method
    evidence.md             Evidence and verification
    skills/<name>/SKILL.md   Task workflow, with references where needed
  knowledge/
    codebases/              Repository map, interfaces and invariants
    infrastructure/         Scheduler architecture and deployment
    environment/            Account configuration and result destinations
    research/               Ideas, derivations, findings and HTML artifacts
  archive/                  Historical material
```

A paper-reading report workflow belongs to harness. Its research conclusions
belong to knowledge. A dataset schema belongs to knowledge; the procedure for
uploading and validating a dataset belongs to a skill that links to that schema.

Mixed pages have been split along these boundaries. Old top-level topic paths
and `research/` remain redirects so existing checkout instructions and notes
continue to resolve. They contain no duplicate rules; edit the canonical target.
The former root README's experiment observations are preserved in
[research knowledge](knowledge/research/trapezoid-schedule-observations.md).

For future edits, use [maintain-wiki](harness/skills/maintain-wiki/SKILL.md).
