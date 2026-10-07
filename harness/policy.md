# Workspace Policy

## Global Rules

Most rules are owned in full by the page named beside them. These are the ones
expensive enough to state twice.

**With the user, write plain language, not agent jargon.** Converse in Chinese,
and write wiki pages and code artifacts in English; paper reports are the
exception ([harness/skills/paper-reading/SKILL.md](skills/paper-reading/SKILL.md)). Lead with the outcome, and say it the way you
would to a colleague who does not read your logs. Name what happened rather than
the internal state name for it. Spell out an identifier the first time it
appears, but keep literal names (a job id, a TPU name, a zone), because they are
what the user greps for.

**Push only when the user's current request explicitly asks for a push.**

**Never destroy the user's work.** Preserve user changes: never revert,
overwrite, or clean a dirty worktree as collateral work. Before deleting shared
or local data, identify the filesystem, owner, active references, and recovery
path, and use a manifest for shared or bulk deletion ([harness/skills/storage-cleanup/SKILL.md](skills/storage-cleanup/SKILL.md)).

**Debug locally, then with one small remote run, before a real run.** After any
large code change, run the checkout's local debug runner (`local_debug.sh` in the
VLM checkouts), then one small remote debug run (`debug_remote.sh`) on a card you
own, and only then queue through `infra`. A remote round trip costs a staged
snapshot, a queue wait, and a card, and most of what dies there dies locally too
([harness/skills/vlm-debug/SKILL.md](skills/vlm-debug/SKILL.md)).

**Keep compute next to its data.** Avoid cross-region or cross-zone data and
checkpoint access; if payload access is necessary, first prove compute and
storage locality. Cross-region copying costs money and is off by default; only a
one-time small copy, such as one checkpoint, is allowed ([harness/skills/infra-operations/SKILL.md](skills/infra-operations/SKILL.md)).

**Treat external writes as transactions.** Establish identity and target,
validate assumptions, write the smallest scope, then read back the result
([harness/engineering.md](engineering.md#external-writes-are-transactions) §External writes are transactions; mail in [harness/skills/mit-email/SKILL.md](skills/mit-email/SKILL.md)).

**Re-read the sheet before logging a result.** Read the tab's header and
neighboring rows every time: the layout drifts, and a stale column map files a
number in the wrong place without an error. Place the row before filling it, keep
cells short, and treat formatting as part of the result ([harness/skills/result-logging/SKILL.md](skills/result-logging/SKILL.md)).

**Repository-local instructions own code semantics.** Follow a repository's own
`AGENTS.md` or `CLAUDE.md` for project-specific code semantics. The shared infra,
locality, storage, and external-write rules here supersede stale operational
sections in old project notes. Surface any remaining conflict rather than
guessing.
