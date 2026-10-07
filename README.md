# Workspace Harness And Knowledge

This directory holds two kinds of maintained content. Agents start at
[AGENTS.md](AGENTS.md); humans can browse the indexes below.

| Location | Purpose |
|---|---|
| [harness/](harness/README.md) | How agents should work: shared rules and task skills |
| [knowledge/](knowledge/README.md) | What is known about the user's codebases, infrastructure, environment, and research |
| [tools/](tools/README.md) | Executable helpers (price caps, the budget gate) |
| [archive/](archive/README.md) | Historical snapshots and supporting evidence; never default instructions |

```text
wiki_agents/
  AGENTS.md                  Agent bootstrap and task router
  harness/
    policy.md                Rules for every task
    engineering.md           Working method
    evidence.md              Evidence and verification
    skills/<name>/SKILL.md   One task workflow each, with references/ where needed
  knowledge/
    codebases/               Checkout map; each checkout's invariants, metrics, findings
    infrastructure/          Cluster, scheduler, market, budget, storage, tpu tooling
    environment/             Workstation, GCP GPU VMs, results workbooks
    research/                Research idea page
  tools/                     Executable helpers
  archive/                   Historical material
```

A procedure for doing a task belongs to the harness; a fact about a system
belongs to knowledge, and the skill links to it. The former top-level pages and
the `jobs/`, `infra/`, `projects/`, `research/`, and `reports/` directories
remain as redirect stubs, because code and notes in other checkouts cite those
paths and their `§` headings. They contain no rules; edit the canonical target.

For future edits, use [maintain-wiki](harness/skills/maintain-wiki/SKILL.md).
