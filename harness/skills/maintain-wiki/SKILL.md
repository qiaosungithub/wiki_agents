---
name: maintain-wiki
description: Add, revise, or reorganize workspace harness instructions and knowledge while preserving source ownership, user edits, and references.
---

# Maintain The Workspace Wiki

This skill owns organization and editing of `wiki_agents/`. The directory index
is [README.md](../../../README.md); task routing is [AGENTS.md](../../../AGENTS.md).

## Classify before writing

**Separate instructions for doing work from knowledge about the user's systems
and research.**

| Content | Canonical home |
|---|---|
| Shared behavior, authorization, engineering and evidence rules | `harness/` |
| Reusable task workflow and conditional procedures | `harness/skills/<name>/SKILL.md` and supporting references |
| Repository architecture, interfaces, dataset schemas, metric definitions | `knowledge/codebases/` |
| Deployment model and infrastructure facts | `knowledge/infrastructure/` |
| Account configuration and project result destinations | `knowledge/environment/` |
| Research questions, derivations, findings and associated artifacts | `knowledge/research/` |
| Superseded guides and dated operational evidence | [archive/](../../../archive) |

A codebase invariant remains knowledge even when phrased as a constraint.
An action sequence is harness even when it applies to only one codebase.
Split mixed pages at meaningful boundaries and link the workflow to the facts
it needs. Do not duplicate environment facts inside skill instructions.

Keep each fact in one canonical location. Root legacy pages are compatibility
redirects, not a second documentation tree. New references must use canonical
paths. Update the relevant index and [AGENTS.md](../../../AGENTS.md) routing when adding a capability;
load only the skill and knowledge needed for the current task.

Record durable decisions and non-obvious invariants, not live job state. Preserve
research reasoning and supporting artifacts in knowledge; put incident timelines,
commands and operational audit snapshots in the archive. Recheck live state when
it matters. Current user instructions, code, and observations outrank memory.

## Writing A Page

### Shape a page by the kind of thing it says

**Divide a page by the kind of content, in the order principle, procedure,
problems, never by the order you learned it.**

| Part | Holds | On an infra page | On a research page |
|---|---|---|---|
| Principle | How it works; what each term and number means | Principle | Setting |
| Procedure | The steps to do it | Usage | Research |
| Problems | What goes wrong and the fix, or what the experiments showed | Errors | Findings |

For a long knowledge page or supporting reference, this skeleton is available when it improves navigation:

- A first paragraph saying what the page owns and naming its sibling pages.
- One sentence listing the chapters: "Chapter 1 is ...; Chapter 2 is ...".
- `## Chapter N — Title` headings separated by `---`, with `###` sections under them.

Skill entrypoints use YAML `name` and `description`, then concise task instructions.
Indexes and short pages do not need chapters.

### Write each section so the reader can stop early

**Open each section with its rule as one bold sentence, so a reader who stops
there is still right; nothing else in the section is bold.**

- Put a caveat inside the sentence it qualifies, never in the paragraph after it. People quote the bold claim alone, so a downstream "(unverified)" is lost in the first retelling. When a finding has two branches, name both in one clause.
- Use a table for parallel cases, such as symptom, cause, and fix, instead of five look-alike bullets.
- Write plain sentences: no literary metaphor, no aphorism, no bolded paragraph, no em-dash chains, no sentence over 40 words.
- Spell out an identifier the first time it appears, but keep its literal name, because that is what people grep for.

### Keep it true

**When a fact stops being true, delete it; never append "but now actually".** A
note carrying both the old and the new answer makes the reader hold both, and
the wrong half travels as far as the right one. Git history keeps what you
delete.

### Rewrite a page without losing a fact

**A migration must preserve existing facts and user changes; a substantive rewrite
must account for intentional additions and removals requested by the user.**

1. Snapshot the current file, uncommitted edits included, before touching it. Carry any uncommitted change into the new text instead of writing over it.
2. Rewrite section by section, and keep fenced code blocks byte-identical.
3. Extract protected tokens from the old and the new text: code spans, numbers, paths, URLs, and headings. Account for each removed token as a relocation, corrected link, or intentional content change.
4. Run the reverse check: list tokens that are new, or more frequent, in the output. A sub-edit can rewrite one fact into a wrong one, and a loss check cannot see that.
5. Resolve every `§` reference in the wiki against the real headings, and every relative path against the real files.
6. If anyone else wrote to the file during the rewrite, validate the draft against the current file, not your snapshot.

---

## How A Rewrite Silently Loses Facts

**Each of these passes a casual read, which is why steps 3 to 6 above are
mechanical.**

| Failure | Why a reader misses it | Guard |
|---|---|---|
| A fact is reworded into a different fact: `41 had an id, 5 did not` became `44 / 2` | Nothing is missing, so a loss check passes | The reverse check for new or changed numbers |
| A section is renamed and other pages still cite the old name | The renamed page reads fine; the pointer elsewhere names nothing | Resolve every `§` reference after a rename |
| A reference is truncated at the first comma or colon | It still looks like a heading | Resolve against the full heading text |
| Another writer edits the file mid-rewrite | Your snapshot is stale, and your write drops their change | Re-read the live file before writing, and merge |
| A hand-maintained count sits next to what it counts ("Three traps" over a four-row table) | It was right when written | Do not write the count |
| A sentence is compressed into telegraphic fragments | It passes every token check | Prefer a plain sentence over the last few percent of compression |
