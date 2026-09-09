# Paper Deep Reading

Read this when producing a paper deep-reading report. Reports live in
`readings/tutorials/` and use that directory's established HTML template. Write
the body in Simplified Chinese while keeping technical names and identifiers in
English. HTML/PDF layout and figure rendering rules are in `paper_rendering.md`.

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

### Cross-links to sibling reports

The reports form a collection, not a pile. Where a claim genuinely touches
another report already in `tutorials/`, link it inline with a plain
`<a href="<slug>_deep_reading.html">…</a>` and one clause saying what the reader
would get by following it — a shared mechanism, a contradicting measurement, the
same idea on a different axis. Do not add a link the argument does not need, and
do not collect links into a "related work" appendix; the value is that the link
sits at the sentence that earned it. Before delivering, confirm every such href
resolves to a file that exists.

### Citation count and age (required in every report)

Item 1 above must additionally carry two numbers, in the §① metadata block:

1. **Citation count, with the source named and the date you looked it up.** Counts
   move, so an undated count is unusable later, and the indices disagree by an
   order of magnitude, so an unattributed one is worse. Write it as
   `被引 137 次（Semantic Scholar，@2026-08-13）`.
2. **Time since first public release**, computed from the **v1** date (not the
   version you read). Write it as `v1 距今 7 个月`; when you read a later version,
   give both dates so the reader can see the revision gap.

Report the two together and never in isolation — a bare count says nothing until
it is divided by age. For anything under ~2 years old, add the rate
(`≈19 次/月`). When the paper is younger than ~3 months, say plainly that the
count carries no signal yet rather than presenting it as evidence.

Citation count is metadata, not evidence. It may not appear in the critique or
the assessment of the method — a well-cited paper does not get an easier reading.

#### Where to get the numbers

**Settled empirically on 2026-08-14 by probing every channel. Do not re-derive,
and do not "improve" it by reaching for a source that responds faster.**

| Channel | Status | Nature |
|---|---|---|
| **Semantic Scholar API** | **429, clears on retry** | **The only usable source.** See below |
| Google Scholar | 403 | **Bot-blocked, not throttled** — 403 from this machine *and* from WebFetch's egress, so waiting and switching networks are both pointless. Never try it first |
| OpenReview API (`api` + `api2`) | 403 | WAF challenge. Has no citation counts anyway |
| OpenAlex | 200 | **Blacklisted, see below** |
| Crossref | 200 | No arXiv DOIs at all (`10.48550/arXiv.*` → 404). Journals only |
| DBLP | 200 | Never carries citation counts. Also lags on new venues |

**S2's 429 is a shared unauthenticated pool, not a per-IP ban** — WebFetch gets
the same 429. It clears on its own: measured 7×429 then 200 at ~2.5 min of 20 s
spacing, with later queries landing on attempts 6 and 4. **Retry to 200 at
~18–20 s spacing, up to ~15 attempts**, before declaring it unavailable:

```bash
s2get () { for i in $(seq 1 15); do
    c=$(curl -s -m 25 -o s2.json -w "%{http_code}" "$1")
    [ "$c" = "200" ] && { cat s2.json; return 0; }; sleep 18
  done; echo "FAILED, last HTTP:$c"; }

# by title — works for papers with no arXiv id at all
s2get "https://api.semanticscholar.org/graph/v1/paper/search/match?query=<full title>&fields=title,citationCount,year,venue,externalIds"
# then by the paperId it returns, for the full record
s2get "https://api.semanticscholar.org/graph/v1/paper/<paperId>?fields=title,citationCount,influentialCitationCount,referenceCount,year,publicationDate,venue,authors"
```

**Query by title, not by arXiv id.** `search/match` resolves papers the id
lookup cannot reach at all — an OpenReview-only paper with no id of any kind
(the ICML 2026 SPT paper) came back this way.

**A 404 from both is a real answer: the paper is not in S2.** Verified
2026-08-14 on TRM (arXiv:2510.04871) — id lookup 404, `search/match` on the full
title 404, and a keyword `paper/search` returned ten hits that were all papers
*citing* it rather than TRM itself. Report that cell as **未收录 / not indexed**,
which is a different statement from "lookup failed", and say which of the three
queries you ran. Do not fill the gap from another index.

**Never substitute OpenAlex or Crossref.** They are reachable with no rate limit,
which is exactly what makes them tempting and wrong. Measured against S2 the same
day: **Huginn 2 vs 317, HRM 3 vs 133** — they mostly miss arXiv→arXiv citations.
OpenAlex additionally fails *silently*: `search=` returned InstructGPT as the top
hit for Coconut's title and a 2006 statistics paper for HRM's, and its
`works/doi:` record for an arXiv preprint can be mis-linked to a different title
outright. **A wrong number is worse than a missing one.**

#### When the paper genuinely has no identifier

A very new conference paper can have **no arXiv id, no DOI, and no proceedings
page** — PMLR volumes 404 for a long time after the conference (ICML 2026's v306
was still the only hole in an otherwise continuous v305/v307 sequence five weeks
after the poster session). With no identifier there is no hook for any index, so
Crossref/OpenAlex/DBLP/web search will all legitimately return zero hits. **Stop
hunting there and go to S2 by title** — S2 crawls PDFs directly and usually has a
bare stub record: correct title, authors and `referenceCount`, but empty `venue`,
`year` and `publicationDate`. Report that stub's count and **say it is a stub**,
so a `0` reads as "real but very fresh" rather than "not indexed".

**For the age half in that situation**, the conference virtual site carries the
exact date and is reachable: grep `icml.cc/virtual/<year>/papers.html` for the
title to get the poster id, then read the date off
`icml.cc/virtual/<year>/poster/<id>` (NeurIPS/ICLR are the same shape). Prefer
this over the PDF's production date, which can be a couple of months early.

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
