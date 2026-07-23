# Paper Deep Reading

Read this when producing a paper deep-reading report. Reports live in
`readings/vision-related/tutorials/`, are registered in that directory's
`index.html`, and use its established HTML template. Write the body in Simplified
Chinese while keeping technical names and identifiers in English. HTML/PDF
layout and figure rendering rules are in `paper_rendering.md`.

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

## Operational Definitions Before Results

Do not assume that an overloaded term has one shared meaning. On first use of a
term such as *task*, *world model*, *step*, etc., you need to explain it concretely.

Overall, you need to try your best to minimize any ambiguity in your report.

### Nested recurrence and test-time scaling

For recurrent, iterative, hierarchical, or adaptive-compute models, never report
a compact tuple such as `H/L = 3/6` without expanding its operational meaning.
Give executable nesting or an explicit timeline, and state all of the following:

1. What one update at each level changes: a latent state, an output proposal, or
   model parameters. Do not use the bare word *update* for all three.
2. Which loop counts are runtime hyperparameters versus architectural or learned
   quantities, and the concrete values used in each reported experiment.
3. Where parameters are shared: across timesteps/cycles, across hierarchy levels,
   across supervision segments, or not at all. Distinguish “two states” from “two
   parameter sets.”
4. Which loop is actually enlarged for reported test-time scaling, which inner
   counts remain fixed, and the resulting total number of inner updates in at
   least one concrete configuration.
5. At which boundary the model decodes an answer, measures convergence, detaches
   state, computes a loss, takes an optimizer step, halts, or resets. Two loop
   schedules with equal raw compute need not be the same protocol when these
   boundary operations differ.

If a paper overloads words such as *step*, *iteration*, *outer loop*, *cycle*, or
*segment*, explicitly flag the collision and introduce unambiguous report-local
names before presenting results.

## **Experimental settings** are required for a table / figure in the paper

For each figure / table, you need to find out the key concrete setting for this. For example the setting includes:

1. The task and exact experimental setting being held fixed or changed.
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
