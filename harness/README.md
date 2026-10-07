# Agent Harness

Shared behavior lives in [policy](policy.md), [engineering](engineering.md), and
[evidence](evidence.md). Task skills describe actions and link to system knowledge.

## Task Skills

| Skill | Use |
|---|---|
| [infra-operations](skills/infra-operations/SKILL.md) | Queue, inspect, resume, and clean up TPU jobs through unified infra; use for scheduler operations and job triage. |
| [vlm-debug](skills/vlm-debug/SKILL.md) | Validate VLM training, checkpoint, resume, or evaluation changes locally and with a small remote run before a real training job. |
| [vlm-data-operations](skills/vlm-data-operations/SKILL.md) | Upload, validate, or mirror VLM training and evaluation data using the workspace uploader and region-local artifact contracts. |
| [mit-email](skills/mit-email/SKILL.md) | Read, search, draft, or send MIT account email; sending requires the user to explicitly authorize sending. |
| [result-logging](skills/result-logging/SKILL.md) | Record experiment conclusions in the correct shared spreadsheet with comparable metrics, provenance, intentional formatting, and read-back verification. |
| [storage-cleanup](skills/storage-cleanup/SKILL.md) | Reclaim disk space or verify artifact and mirror completeness while preserving active jobs and recoverable data. |
| [experiment-loop](skills/experiment-loop/SKILL.md) | Manage an ongoing research experiment loop, retain run provenance, and compare results under matched protocols. |
| [paper-reading](skills/paper-reading/SKILL.md) | Write a hierarchical paper deep-reading report with clear central messages, complete deeper explanations, and a final Agent comment chapter. |
| [maintain-wiki](skills/maintain-wiki/SKILL.md) | Add, revise, or reorganize workspace harness instructions and knowledge while preserving source ownership, user edits, and references. |

Read only the selected skill and the references needed for the task. These are
workspace-local skills routed by [AGENTS.md](../AGENTS.md), not global installations.
