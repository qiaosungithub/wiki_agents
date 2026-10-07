# Workspace Agent Bootstrap

Read this entry before work under `/kmh-nfs-ssd-us-mount/code/qiao/work`.
This wiki separates agent harness from knowledge about the user's systems.

## Start Here

1. Read [workspace policy](harness/policy.md), [engineering discipline](harness/engineering.md), and [evidence rules](harness/evidence.md).
2. For repository work, use the [checkout map](knowledge/codebases/projects.md) and the checkout's own `AGENTS.md` or `CLAUDE.md`.
3. Select the task skill and only the knowledge needed for it from the router below. Do not load the whole wiki.
4. Inspect current code, git state, and relevant live state before acting. User instructions and current evidence outrank this wiki.

## Ownership

| Layer | Owns | Entry |
|---|---|---|
| Harness | Shared behavior and executable task guidance | [Harness](harness/README.md) |
| Knowledge | Codebase contracts, environment facts, research ideas and findings | [Knowledge](knowledge/README.md) |
| Archive | Historical evidence, never default instructions | [Archive](archive/README.md) |

A task skill explains how to do the work and links to the knowledge it needs.
Knowledge describes the user's systems and research; it does not become a
universal agent instruction merely because an agent reads it. Local codebase
invariants still constrain changes to that codebase.

## Task Router

| Task | Skill or shared method | Relevant knowledge |
|---|---|---|
| Add or reorganize wiki content | [Maintain wiki](harness/skills/maintain-wiki/SKILL.md) | [Knowledge index](knowledge/README.md) |
| Write a paper report | [Paper reading](harness/skills/paper-reading/SKILL.md); its [rendering reference](harness/skills/paper-reading/references/rendering.md) for HTML/PDF | [Research context](knowledge/research/README.md) when a connection is relevant |
| Queue, inspect, resume or clean TPU jobs | [Infra operations](harness/skills/infra-operations/SKILL.md) | [Infra architecture and deployment](knowledge/infrastructure/unified-infra.md) |
| Change VLM training, resume or eval | [VLM validation](harness/skills/vlm-debug/SKILL.md) | [Training contracts](knowledge/codebases/vlm-training.md), [data contracts](knowledge/codebases/vlm-data.md) |
| Upload, validate or mirror VLM data | [VLM data operations](harness/skills/vlm-data-operations/SKILL.md) | [Data contracts](knowledge/codebases/vlm-data.md) |
| Interpret a VLM benchmark | [Evidence rules](harness/evidence.md) | [Metric definitions](knowledge/codebases/vlm-metrics.md) |
| Log experiment results | [Result logging](harness/skills/result-logging/SKILL.md) | [Workbooks](knowledge/environment/result-workbooks.md); [VLM metrics](knowledge/codebases/vlm-metrics.md) for VLM results |
| Manage an experiment program | [Experiment loop](harness/skills/experiment-loop/SKILL.md) | [Research context](knowledge/research/README.md) |
| Reclaim space or verify artifacts | [Storage cleanup and integrity](harness/skills/storage-cleanup/SKILL.md) | [Infra](knowledge/infrastructure/unified-infra.md), relevant producer contracts |
| Read, draft or send MIT email | [MIT email](harness/skills/mit-email/SKILL.md) | [Account and services](knowledge/environment/mit-email.md) |
| Study per-site optimization | Load a task skill only if taking action | [Research idea](knowledge/research/looped_nanogpt_per_site.md) and [derivations](knowledge/research/README.md) |

## Paths And Compatibility

Markdown links are relative to their containing file. Literal runtime paths and
commands retain their original workspace or repository context. Old root topic
pages and `research/` are compatibility redirects; follow them to the canonical
location and use canonical paths in new links. Archives preserve original text
and may name historical paths.

Skills are maintained locally under `harness/skills/` and selected through this
router. This reorganization does not install them into a global skill directory.
