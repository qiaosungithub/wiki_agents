# Writing Memory Into This Wiki

Owns how `wiki_agents/` is organized and how to add to it or rewrite a page.
`AGENTS.md` §Maintaining Memory keeps the short rule list; this page is the
model behind it and the rewrite procedure.

Chapter 1 is how the wiki is shaped; Chapter 2 is how to write a page; Chapter 3
is how a rewrite silently loses facts.

---

## Chapter 1 — How The Wiki Is Shaped

### What the files are for

**These files exist so a future agent does not repeat a mistake or re-derive
something expensive.** Write only what serves that, and put each fact in exactly
one place.

### The tree

**A reader starts at `AGENTS.md`, follows its router to one page, and reads only
that page, so a fact must land in the page that reader will open.**

| Level | Owns |
|---|---|
| `AGENTS.md` | The root: rules for every task, the evidence rules, and the router to every other page |
| Method pages: `engineering.md`, `memory.md` | How to work on any task, and how to write this wiki |
| Topic pages | One area each, such as `infra.md` or `storage.md` |
| `projects.md` and project pages | The checkout map, and one page per checkout family, such as `vlm_training.md` |
| `research/` | Research idea pages |
| `archive/` | History, never routed to by default |

### Worth keeping or not

**Write a rule only if a future agent cannot cheaply work it out from the code,
or if getting it wrong costs real time.**

- Write the rule, not the story. Keep one short clause of evidence if it makes the rule believable; forensics go to git history or `archive/`.
- Prefer the abstract statement. A note that only makes sense for one paper or one job belongs in a project page or the archive.
- No diary: no "fixed on <date>", job ids, row numbers, or source line numbers, and no "still running" or "as of today". Record how to verify the state instead.
- Dated audit evidence (scan counts, validation numbers, status snapshots) goes under `archive/audits/`; the page keeps the derived rule and a pointer.

### Where a fact goes

**Every fact has one home; every other page points at it by file name and
section, and never copies it.**

| The fact is about | Its home |
|---|---|
| Every task | `AGENTS.md` Global Rules or Evidence Order |
| Changing code, testing, reporting a result | `engineering.md` |
| One topic | That topic's page, found through the router |
| One checkout family | Its project page |

If two pages both want a fact, pick one owner and have the other say
`see storage.md §...`. Two copies drift, and then one of them is wrong.
`AGENTS.md` may restate a rule that is expensive to miss, but it names the page
that owns it. When you rename a section, fix every reference to it in the same
edit.

---

## Chapter 2 — Writing A Page

### Shape a page by the kind of thing it says

**Divide a page by the kind of content, in the order principle, procedure,
problems, never by the order you learned it.**

| Part | Holds | On an infra page | On a research page |
|---|---|---|---|
| Principle | How it works; what each term and number means | Principle | Setting |
| Procedure | The steps to do it | Usage | Research |
| Problems | What goes wrong and the fix, or what the experiments showed | Errors | Findings |

A topic or project page follows this skeleton:

- A first paragraph saying what the page owns and naming its sibling pages.
- One sentence listing the chapters: "Chapter 1 is ...; Chapter 2 is ...".
- `## Chapter N — Title` headings separated by `---`, with `###` sections under them.

Hub pages (`AGENTS.md`, `projects.md`, `archive/README.md`) are rules and tables
without chapters.

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

**A rewrite is finished only when a mechanical check shows every fact survived
and no new fact appeared.**

1. Snapshot the current file, uncommitted edits included, before touching it. Carry any uncommitted change into the new text instead of writing over it.
2. Rewrite section by section, and keep fenced code blocks byte-identical.
3. Extract protected tokens from the old and the new text: code spans, numbers, paths, URLs, and headings. Every old token must reappear, unless you dropped it on purpose as diary.
4. Run the reverse check: list tokens that are new, or more frequent, in the output. A sub-edit can rewrite one fact into a wrong one, and a loss check cannot see that.
5. Resolve every `§` reference in the wiki against the real headings, and every relative path against the real files.
6. If anyone else wrote to the file during the rewrite, validate the draft against the current file, not your snapshot.

---

## Chapter 3 — How A Rewrite Silently Loses Facts

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
