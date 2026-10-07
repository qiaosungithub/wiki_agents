# paper-with-agent: writing our paper with the user

The checkout `~/work/paper-with-agent/` holds the paper on the per-site
optimizer idea ([knowledge/research/looped_nanogpt_per_site.md](../research/looped_nanogpt_per_site.md)), written by the user
and agents together. Remote `git@github.com:qiaosungithub/paper-with-agent.git`,
branch `main`. The repo's own `readme.md` owns the full rules. This page gives
the orientation and the workstation facts the readme does not carry.
Working on the paper (starting a session, building and checking the PDF,
sourcing numbers, citations and figures) is the paper-writing skill
([harness/skills/paper-writing/SKILL.md](../../harness/skills/paper-writing/SKILL.md)).

## The Three Layers

**`hie1/` belongs to the user alone: an agent never edits, creates, renames or
deletes anything in it, not even a typo fix.** Each layer has one owner, the
higher layer wins a conflict, and changes flow downward.

| Layer | What it is | Owner | An agent may |
|---|---|---|---|
| `hie1/` | Direction: story, claims, scope, benchmark decisions | User | Read only. Raise problems with the user or in `hie2/open-questions.md` |
| `hie2/` | Blueprint: what each section says, its evidence, figures, terminology | User and agent; the user decides | Write, marking its own additions `[proposed]`; never add a claim or widen the scope beyond hie1 |
| `hie3/` | The paper: LaTeX in the ICML template, plus the compiled `main.pdf` | Agent | Everything, as long as every claim traces to hie2 and every number to a real run |

## The ICML Template

- Template: the official ICML style kit,
  `https://media.icml.cc/Conferences/ICML<year>/Styles/icml<year>.zip`. The kit compiles here
  unmodified. Do not edit `icml<year>.sty` or the `.bst`.
- Page limit: the main body must fit in 8 pages; references, the Impact
  Statement, and appendices do not count, per the kit's own instructions.
  ICML requires an unnumbered Impact Statement before the
  references, and appendices go in the same PDF.
- `\usepackage{icml<year>}` with no option is the anonymous submission mode;
  the style file strips the author block itself. `[accepted]` and `[preprint]`
  both show the authors. Keep acknowledgements, and links to the GitHub repo,
  W&B or the results workbook, out of the paper text.
