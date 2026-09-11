# Writing Memory Into This Wiki

This page explains, in plain terms, how the notes in `wiki_agents/` are
organized, so anything you add keeps the same shape. Read it once before you
write into the wiki. The detailed writing rules live in `AGENTS.md`
§Maintaining Memory; this page is the mental model behind them.

## The one idea

**These files exist so a future agent does not repeat a mistake or re-derive
something expensive. Write only what serves that, and put each thing in exactly
one place.**

Everything below is those two halves: write what is worth keeping, and keep it
findable.

## The shape of the wiki

The wiki is a tree, read from the top down:

- `AGENTS.md` is the root. It holds the rules that apply to every task, and a
  router table that points you to the right topic file.
- Topic files (`storage.md`, `jobs.md`, `engineering.md`, …) each own one area.
- Subdirectories (`jobs/`, `projects/`, `research/`, …) group related files, and
  each has a `README.md` that indexes them.

A reader starts at `AGENTS.md`, follows the router to one file, and reads only
that file. When you write, your job is to make the fact land in the file that
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

## Where does it go?

**Every fact has one home. Put it there, and link to it from anywhere else that
needs it — never copy it.**

- A rule that applies to all tasks → `AGENTS.md`, Global Rules.
- A rule about one topic → that topic's file (use the router to find it).
- A rule about one project → that project's guide under `projects/`.
- If two files both seem to want it, pick one owner and have the other point at
  it by name (`see storage.md §…`). Two copies drift, and then one of them is
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

## Keeping it true

**When a fact stops being true, delete it — do not add "but now actually…".** A
note that carries both the old answer and the new one makes the reader hold both,
and the wrong half travels just as far. Git history is the archive, so deleting
loses nothing.
