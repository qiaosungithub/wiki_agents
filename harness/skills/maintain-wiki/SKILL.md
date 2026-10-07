---
name: maintain-wiki
description: Add to, revise, or reorganize this wiki (`wiki_agents/`), deciding where a note belongs and how to shape the page; use before writing anything into the wiki.
---

# Maintain The Workspace Wiki

This skill explains, in plain terms, how the notes in `wiki_agents/` are
organized and how to write into them, so anything you add keeps the same shape.
Read it once before you write into the wiki. It relies on the router in
[`AGENTS.md`](../../../AGENTS.md) and the rules in
[harness/policy.md](../../policy.md#global-rules). The detailed writing rules are
the checklist in [Maintaining Memory](#maintaining-memory) at the
end; the sections before it are the mental model behind them.

## The one idea

**These files exist so a future agent does not repeat a mistake or re-derive
something expensive. Write only what serves that, and put each thing in exactly
one place.**

Everything below is those two halves: write what is worth keeping, and keep it
findable.

## The shape of the wiki

The wiki is a tree, read from the top down:

- [The root `AGENTS.md`](../../../AGENTS.md) points to the rules that apply to every
  task, and holds a router table that points you to the right skill and
  knowledge page.
- `harness/` holds how to work: the rules for every task, the engineering method,
  the evidence rules, and one task skill per directory under `harness/skills/`.
- `knowledge/` holds what is known, in `codebases/`, `infrastructure/`,
  `environment/`, and `research/`; each page there owns one area.
- Subdirectories group related files, and each has a `README.md` that indexes
  them; a skill directory's entrypoint is its `SKILL.md` instead. `tools/` holds
  executable helpers; `archive/` holds history and is never routed to by default.
- The old top-level topic files and the old `jobs/`, `infra/`, `projects/`,
  `research/` and `reports/` pages are redirect stubs that point at their new
  homes. They hold no rules: edit the canonical target, and use canonical paths
  in new links.

```text
wiki_agents/
  AGENTS.md                  root: start here, task router
  README.md                  directory index
  harness/
    policy.md                rules for every task
    engineering.md           working method
    evidence.md              evidence order and verification
    skills/<name>/SKILL.md   task workflow, with references/*.md where needed
  knowledge/
    codebases/               per-checkout architecture, interfaces, invariants, findings
    infrastructure/          how the cluster, scheduler, storage and tools work
    environment/             machines, accounts, result workbooks
    research/                research ideas and findings
  tools/                     executable helpers
  archive/                   history
```

A reader starts at [`AGENTS.md`](../../../AGENTS.md), follows the router to one skill
or page, and reads only that file. When you write, your job is to make the fact land in the file that
reader will actually open.

## Before you write: is it worth keeping?

**Write a rule only if a future agent cannot cheaply work it out from the code,
or if getting it wrong costs real time.** Everything else is noise that hides the
parts that matter.

- Write the rule, not the story. "Enqueue from the code directory, not `~/work`"
  is a rule. "On Tuesday the build broke because…" is a story. Keep one short
  clause of evidence if it makes the rule believable; the rest belongs in git
  history.
- No diary. No dates, job ids, XIDs, row numbers, or source line numbers; no
  "still running" or "as of today". These read as true for a day and wrong after.

## Classify before writing

**Separate instructions for doing work from knowledge about the user's systems
and research.**

| Content | Canonical home |
|---|---|
| Rules that apply to every task: shared behavior, authorization, engineering and evidence rules | [harness/policy.md](../../policy.md#global-rules), [harness/engineering.md](../../engineering.md), [harness/evidence.md](../../evidence.md#evidence-order) |
| Reusable task workflow, step-by-step procedures, triage and diagnosis drills, "how to do X" | `harness/skills/<name>/SKILL.md`, with `references/*.md` for long supporting detail |
| Repository architecture, interfaces, invariants, metric definitions, what experiments found | `knowledge/codebases/` |
| How the cluster, scheduler, storage and tools work: contracts, measured facts, reference tables | `knowledge/infrastructure/` |
| Machines, accounts, workbooks and result destinations | `knowledge/environment/` |
| Research ideas and findings | `knowledge/research/` |
| Executable helpers; prose lives elsewhere | [`tools/`](../../../tools/README.md) |
| Superseded guides and dated operational evidence | [`archive/`](../../../archive/README.md) |

A codebase or infrastructure invariant remains knowledge even when phrased as a
constraint ("must", "never"). An action sequence is harness even when it applies
to only one codebase. Split mixed pages at meaningful boundaries and link the
workflow to the facts it needs: a skill links to the knowledge it needs and does
not copy it.

Do not create tiny skills. When a page's procedural part is a few lines, it may
stay with its knowledge page; prefer one cohesive skill per task family over many
fragments, and do not create a skill with no real procedure.

When you add a capability, update the relevant index and the router in
[`AGENTS.md`](../../../AGENTS.md). Load only the skill and knowledge
needed for the current task.

## Where does it go?

**Every fact has one home. Put it there, and link to it from anywhere else that
needs it — never copy it.**

- A rule that applies to all tasks → [`harness/policy.md`](../../policy.md#global-rules), Global Rules.
- A rule about one topic → that topic's file (use the router to find it); the
  table in [Classify before writing](#classify-before-writing) says whether it is
  a skill or a knowledge page.
- A rule about one project → that project's page under `knowledge/codebases/`;
  the procedure for running it goes to that project's skill.
- If two files both seem to want it, pick one owner and have the other point at
  it by name, with a relative link to the owning section. Two copies drift, and then one of them is
  wrong.

If you rename a section that other files point at, fix those links too, or the
pointers go dead.

## How to shape a page

**Divide a page by the KIND of thing it says, not by the order you learned it.**
Most pages fall into a few clean parts:

- **Principle** — how it works, and what each term or number means.
- **Procedure** — the steps to actually do it.
- **Bugs, or findings** — what goes wrong and the fix, or what experiments
  showed.

Keep those parts separate and in that order. A reader who wants the "how" should
not have to wade through war stories to reach it.

Small habits that keep a page readable:

- Start each section with its point in one **bold sentence**. A reader who stops
  after that sentence should still be right.
- Use a table when you have several parallel cases (symptom → cause → fix). It
  beats five look-alike bullets.
- Put a caveat inside the sentence it qualifies, not the sentence after. People
  quote the first sentence on its own.
- Keep the top of the file to one line saying what it owns, plus a pointer to its
  hub and siblings.

For a long knowledge page or a skill's supporting reference, this skeleton is
available when it improves navigation:

- A first paragraph saying what the page owns and naming its sibling pages.
- One sentence listing the chapters: "Chapter 1 is ...; Chapter 2 is ...".
- `## Chapter N — Title` headings separated by `---`, with `###` sections under them.

A skill entrypoint, `harness/skills/<name>/SKILL.md`, opens with YAML front
matter: `name:` equal to its directory name, and a one-sentence `description:`
saying what task it is for and when to use it. Then comes `# Title`, a first
paragraph naming the knowledge pages it relies on, and concise sections. Indexes
and short pages do not need chapters.

## Keeping it true

**When a fact stops being true, delete it — do not add "but now actually…".** A
note that carries both the old answer and the new one makes the reader hold both,
and the wrong half travels just as far. Git history is the archive, so deleting
loses nothing.

## Maintaining Memory

**Record a rule only when a future agent cannot cheaply infer it from the code,
or when violating it has a real cost.** Everything else dilutes what matters.

- **Write the rule, not the incident.** Keep the one clause of evidence that
  makes it credible; forensics go to `archive/`, or to git history.
- **Prefer the abstract statement.** A note that only makes sense for one paper
  or one job id belongs in a project guide or the archive.
- **One canonical owner per rule**; everyone else points at it by file name.
- **Replace stale facts; never append a diary.** No "fixed on <date>", no live
  state, no source line numbers, no job ids. Record how to verify instead.
- **Lead a section with its rule in bold.** A reader who stops after the first
  sentence must not be misled.
- **Put the caveat inside the sentence it qualifies, never in the paragraph
  after it.** People quote and act on the bold claim alone, so a qualifier
  parked downstream — "but it may also be X", "(unverified)" — is reliably lost
  in the first retelling, and what survives is more confident than what you
  wrote. When a finding has two branches, name both in one clause so that
  whichever half is copied still carries the other.
- **Prefer a table to five parallel bullets.** Delete audit snapshots once they
  are too old to be evidence.
- **Write plain sentences, not the house dialect.** No literary metaphor, no
  aphorism, no bolding a whole paragraph, no em-dash chains, no 40-word
  sentences. One bold phrase per section, for the rule. This is the same
  standard as the user-facing one in [harness/policy.md](../../policy.md#global-rules), and it is why the guides read the way
  they do.
- **When a fact stops being true, delete it; do not append a correction.** A
  note that says "X, but actually now Y" makes the reader hold both, and the
  wrong half travels just as far. Cut what is dead: git history is the archive
  ([archive/README.md](../../../archive/README.md)).
