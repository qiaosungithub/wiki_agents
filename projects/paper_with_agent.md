# paper-with-agent: writing our paper with the user

The checkout `~/work/paper-with-agent/` holds the paper on the per-site
optimizer idea (`../research/looped_nanogpt_per_site.md`), written by the user
and agents together. Remote `git@github.com:qiaosungithub/paper-with-agent.git`,
branch `main`. The repo's own `readme.md` owns the full rules. This page gives
the orientation and the workstation facts the readme does not carry.

## The Three Layers

**`hie1/` belongs to the user alone: an agent never edits, creates, renames or
deletes anything in it, not even a typo fix.** Each layer has one owner, the
higher layer wins a conflict, and changes flow downward.

| Layer | What it is | Owner | An agent may |
|---|---|---|---|
| `hie1/` | Direction: story, claims, scope, benchmark decisions | User | Read only. Raise problems with the user or in `hie2/open-questions.md` |
| `hie2/` | Blueprint: what each section says, its evidence, figures, terminology | User and agent; the user decides | Write, marking its own additions `[proposed]`; never add a claim or widen the scope beyond hie1 |
| `hie3/` | The paper: LaTeX in the ICML template, plus the compiled `main.pdf` | Agent | Everything, as long as every claim traces to hie2 and every number to a real run |

## Starting A Session

1. Read `readme.md`, then all of `hie1/`, then all of `hie2/`.
2. Run `git status`. The user edits hie1 directly and may leave it uncommitted.
   Commit a user's hie1 edit only when asked, and never inside an agent commit.
3. Talk with the user in Chinese. hie2 may mix Chinese and English; text meant
   for the paper, and the paper itself, is English.

## Building The Paper

**Build with plain `pdflatex` and `bibtex`; `latexmk` is not installed on the
workstation.**

- Template: the official ICML style kit,
  `https://media.icml.cc/Conferences/ICML<year>/Styles/icml<year>.zip`. A year
  that is not yet published returns HTTP 404, so probe with
  `curl -s -o /dev/null -w '%{http_code}' <url>`, use the newest year that
  answers 200, and switch once the target year appears. The kit compiles here
  unmodified. Do not edit `icml<year>.sty` or the `.bst`.
- Build from `hie3/`:
  `pdflatex -interaction=nonstopmode main && bibtex main && pdflatex -interaction=nonstopmode main && pdflatex -interaction=nonstopmode main`.
  Then grep `main.log` for lines starting with `!` and for `undefined`
  references or citations. A PDF being written does not mean it is clean.
- Page limit: the main body must fit in 8 pages; references, the Impact
  Statement, and appendices do not count, per the kit's own instructions.
  `pdfinfo main.pdf` counts everything, so check the page where the main body
  ends instead. ICML requires an unnumbered Impact Statement before the
  references, and appendices go in the same PDF.
- `\usepackage{icml<year>}` with no option is the anonymous submission mode;
  the style file strips the author block itself. `[accepted]` and `[preprint]`
  both show the authors. Keep acknowledgements, and links to the GitHub repo,
  W&B or the results workbook, out of the paper text.

## Numbers, Citations, Figures

**Every number in hie3 comes from a logged run and carries its source (tab, run
name) in a LaTeX comment beside it.** Never quote a number from memory or from
chat. Looped-nanoGPT results live in the tab `../research/result_logging.md`
§Which Tab routes to, and that file owns the column meanings.

- Every citation must be a real paper whose bibliographic entry you have checked.
  When a claim needs a citation you cannot verify, leave `\todo{}`.
- `plots/` holds the user's sketches and screenshots. They are reference
  material, never overwritten. Final figures go in `hie3/figures/`, next to the
  script or source that produces them.
