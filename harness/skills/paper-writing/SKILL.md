---
name: paper-writing
description: Work on the paper in `~/work/paper-with-agent`: start a session, build the ICML PDF with pdflatex/bibtex and check it, and give every number, citation and figure a verified source.
---

# Writing The Paper

Relies on [knowledge/codebases/paper-with-agent.md](../../../knowledge/codebases/paper-with-agent.md) for the three layers and who may
edit each (`hie1/` is user-only) and for the ICML template rules,
and on [knowledge/environment/result-workbooks.md §Which Tab](../../../knowledge/environment/result-workbooks.md#which-tab) for where the looped-nanoGPT numbers live.

## Starting A Session

1. Read `readme.md`, then all of `hie1/`, then all of `hie2/`.
2. Run `git status`. The user edits hie1 directly and may leave it uncommitted.
   Commit a user's hie1 edit only when asked, and never inside an agent commit.
3. Talk with the user in Chinese. hie2 may mix Chinese and English; text meant
   for the paper, and the paper itself, is English.

## Building The Paper

**Build with plain `pdflatex` and `bibtex`; `latexmk` is not installed on the
workstation.**

- Template year: a year that is not yet published returns HTTP 404, so probe the
  kit URL ([The ICML Template](../../../knowledge/codebases/paper-with-agent.md#the-icml-template)) with
  `curl -s -o /dev/null -w '%{http_code}' <url>`, use the newest year that
  answers 200, and switch once the target year appears.
- Build from `hie3/`:
  `pdflatex -interaction=nonstopmode main && bibtex main && pdflatex -interaction=nonstopmode main && pdflatex -interaction=nonstopmode main`.
  Then grep `main.log` for lines starting with `!` and for `undefined`
  references or citations. A PDF being written does not mean it is clean.
- Page limit ([The ICML Template](../../../knowledge/codebases/paper-with-agent.md#the-icml-template)):
  `pdfinfo main.pdf` counts everything, so check the page where the
  main body ends instead.

## Numbers, Citations, Figures

**Every number in hie3 comes from a logged run and carries its source (tab, run
name) in a LaTeX comment beside it.** Never quote a number from memory or from
chat. Looped-nanoGPT results live in the tab [knowledge/environment/result-workbooks.md §Which Tab](../../../knowledge/environment/result-workbooks.md#which-tab) routes to, and the result-logging skill ([result-logging skill](../result-logging/SKILL.md)) owns the column meanings.

- Every citation must be a real paper whose bibliographic entry you have checked.
  When a claim needs a citation you cannot verify, leave `\todo{}`.
- `plots/` holds the user's sketches and screenshots. They are reference
  material, never overwritten. Final figures go in `hie3/figures/`, next to the
  script or source that produces them.
