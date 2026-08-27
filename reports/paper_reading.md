# Paper Deep Reading

Read this when producing a paper deep-reading report. Reports live in
`work/reports/`, written in Simplified Chinese with technical names and
identifiers in English (`README.md`). Layout and figure rendering are
`rendering.md`; the general "define your terms" discipline `../engineering.md`.

## Required Story

**A report must let a reader understand the paper with no prior topic context**,
so never substitute a summary for technical explanation. Preserve complete
authorship, and keep the paper's claims distinct from the report's inference.

| # | The report must carry |
|---|---|
| 1 | Exact title, authors, affiliations, date/version, venue, arXiv id, local PDF, project/code links; a prominent Demo/链接 block, and any video demo linked with a clear 🎬 marker |
| 2 | A plain-language conclusion: problem, key insight, claimed result, why it matters to the user's research |
| 3 | Task definition: inputs, outputs, setup, metrics |
| 4 | Method, concrete recipe, and all reported ablations — native HTML tables and real paper figures where they add evidence |
| 5 | Broader impact, actual follow-up directions, a technically grounded critique of limitations |
| 6 | Connections to the user's AR optical-flow/diffusion rendering, confidence-routed generation, and image/video generation work |

## Kill Ambiguity Before Reporting Any Result

**The report's job is to be unambiguous, not merely complete.**

**Define an overloaded term on first use** — *task*, *step*, *update*,
*iteration*, *cycle*, *segment*, *world model* have no shared meaning, so say
what the thing is and what it changes. When a paper uses one word for several
distinct things, **flag the collision and introduce unambiguous report-local
names before presenting any number that depends on it**.

**Never pass through a compact notation without expanding it**: a tuple, a
shorthand like `H/L = 3/6`, or a named configuration means nothing to the
reader. Expand it into an executable description or explicit timeline, and for a
nested or repeated structure state what one unit of work at each level changes
(a state, an output, or the parameters — never the bare word *update* for all
three), which counts are free hyperparameters versus architectural or learned
quantities and their concrete value in each reported experiment, where things
are shared versus duplicated ("two states" is not "two parameter sets"), which
knob is enlarged for a scaling claim with what held fixed and the resulting
total in one concrete configuration, and at which boundary the system answers,
measures convergence, cuts gradients, computes a loss, takes an optimizer step,
halts, or resets. **Two schedules with equal raw compute are not the same
protocol when those boundaries differ.**

## Every Figure And Table Needs Its Experimental Setting

**A number the reader cannot situate is not evidence.** For each figure and
table establish:

| Establish | Detail |
|---|---|
| The task | Exactly what is held fixed versus varied |
| What the graphics denote | Axes, rows, columns, colors, curves, markers, method names, panels; expand genuinely nonstandard abbreviations on first use |
| What each number counts | Metric definition, unit, denominator/evaluation population, aggregation over examples/seeds/views, higher-or-lower-is-better, plus any protocol distinction that changes its meaning (frozen probe vs fine-tuning, per-video single-view vs multi-view, success per episode vs per subgoal) |
| One argument-carrying example | Value, matched baseline, absolute or relative change. Translate a decimal such as `0.90` into a count only when the denominator is actually known |
| What it does and does not support | Separate causal ablations from cross-paper or unmatched comparisons |

**If labels are unreadable at report scale, crop or enlarge the panel,
transcribe its values into searchable HTML, or omit the figure** — never make
the reader reverse-engineer a thumbnail.
