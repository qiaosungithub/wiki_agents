# Paper Deep Reading

Read this when producing a paper deep-reading report. Reports live in
`work/reports/`. Write the body in Simplified Chinese, keeping technical names
and identifiers in English. Layout and figure rendering are in `rendering.md`;
the general "define your terms" discipline is in `engineering.md`.

## Required Story

A report should let a reader understand the paper without prior topic context:

1. Exact title, authors, affiliations, date/version, venue, arXiv id, local PDF,
   and project/code links. Include a prominent Demo/链接 block; when the paper
   has a video demo, link it with a clear 🎬 marker.
2. A plain-language conclusion: problem, key insight, claimed result, and why it
   matters to the user's research.
3. Task definition with inputs, outputs, setup, and metrics.
4. Method, concrete recipe, and all reported ablations. Use native HTML tables
   and real paper figures when they add evidence.
5. Broader impact, actual follow-up directions, and a technically grounded
   critique of limitations.
6. Connections to the user's AR optical-flow/diffusion rendering,
   confidence-routed generation, and image/video generation work.

Do not replace technical explanation with a paper summary. Preserve complete
authorship and distinguish the paper's claims from the report's inference.

## Kill Ambiguity Before Reporting Any Result

The report's job is to be unambiguous, not merely complete. Every rule below is
a special case of that.

**Define an overloaded term on first use.** Words like *task*, *step*, *update*,
*iteration*, *cycle*, *segment*, and *world model* do not have one shared
meaning. Say concretely what the thing is and what it changes. When a paper uses
one word for several distinct things, **flag the collision explicitly and
introduce unambiguous report-local names before presenting any number that
depends on it**.

**Never pass through a compact notation without expanding it.** A tuple, a
shorthand like `H/L = 3/6`, or a named configuration is meaningless to the
reader. Expand it into an executable description or an explicit timeline. For
any process with nested or repeated structure, state:

- what one unit of work at each level actually changes — a state, an output, or
  the parameters — never the bare word *update* for all three;
- which counts are free hyperparameters versus architectural or learned
  quantities, and the concrete values used in each reported experiment;
- where things are shared versus duplicated, distinguishing "two states" from
  "two parameter sets";
- which knob is enlarged for a scaling claim, what stays fixed, and the
  resulting total in at least one concrete configuration;
- at which boundary the system produces an answer, measures convergence, cuts
  gradients, computes a loss, takes an optimizer step, halts, or resets. **Two
  schedules with equal raw compute are not the same protocol when these
  boundaries differ.**

## Every Figure And Table Needs Its Experimental Setting

A number the reader cannot situate is not evidence. For each figure or table,
establish:

1. The task, and exactly what is held fixed versus varied.
2. What the relevant axes, rows, columns, colors, curves, markers, method names,
   and panels denote; expand genuinely nonstandard abbreviations on first use.
3. What each reported number counts: metric definition, unit,
   denominator/evaluation population, aggregation over examples/seeds/views,
   and whether higher or lower is better. Include protocol distinctions that
   change the meaning of the number (for example frozen probe vs fine-tuning,
   per-video single-view vs multi-view, or success per episode vs per subgoal).
4. At least one argument-carrying numerical example: value, matched baseline,
   and absolute or relative change. Translate a decimal such as `0.90` into a
   count only when the denominator is actually known.
5. What the experiment supports and what it does not. Separate causal ablations
   from cross-paper or unmatched comparisons.

If labels are unreadable at report scale, crop or enlarge the relevant panel,
transcribe its values into searchable HTML, or omit the figure; never make the
reader reverse-engineer a thumbnail.
