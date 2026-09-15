# Paper Deep Reading

Owns what a paper deep-reading report must contain. The HTML source, figures, and
PDF rendering are `paper_rendering.md`; file naming and paths under `readings/`
are `readings/README.md`. Reports live in `readings/tutorials/`. Write the body in
Simplified Chinese while keeping technical names and identifiers in English.

Chapter 1 is what every report carries; Chapter 2 is how to report a result
without ambiguity; Chapter 3 is how to get the citation count and age.

---

## Chapter 1 — What Every Report Carries

### Required story

**A report must let a reader understand the paper with no prior topic context, so
never replace technical explanation with a paper summary.** Preserve complete
authorship, and distinguish the paper's claims from the report's inference.

| Part | Contents |
|---|---|
| 1. Metadata | Exact title, authors, affiliations, date/version, venue, arXiv id, local PDF, and project/code links. Include a prominent Demo/链接 block; when the paper has a video demo, link it with a clear 🎬 marker. Carry the citation count and age here too (Chapter 3). |
| 2. Conclusion | In plain language: the problem, key insight, claimed result, and why it matters to the user's research. |
| 3. Task definition | Inputs, outputs, setup, and metrics. |
| 4. Method | The concrete recipe and all reported ablations. Use native HTML tables and real paper figures when they add evidence. |
| 5. Impact and critique | Broader impact, actual follow-up directions, and a technically grounded critique of limitations. |
| 6. Connections | To the user's AR optical-flow/diffusion rendering, confidence-routed generation, and image/video generation work. |

### Cross-links to sibling reports

**Link another report in `tutorials/` only at the sentence whose claim genuinely
touches it.** Use a plain `<a href="<slug>_deep_reading.html">…</a>` and one
clause saying what the reader gets by following it: a shared mechanism, a
contradicting measurement, or the same idea on a different axis. Do not add a link
the argument does not need, and do not collect links into a "related work"
appendix. Before delivering, confirm every such href resolves to a file that
exists.

---

## Chapter 2 — Reporting A Result Without Ambiguity

### Define every overloaded term

**The report's job is to be unambiguous, not merely complete, so never assume an
overloaded term has one shared meaning.** On first use of a term such as *task*,
*world model*, or *step*, explain it concretely.

### Nested recurrence and test-time scaling

**For recurrent, iterative, hierarchical, or adaptive-compute models, never report
a compact tuple such as `H/L = 3/6` without expanding its operational meaning.**
Give executable nesting or an explicit timeline, and state all of the following:

1. What one update at each level changes: a latent state, an output proposal, or model parameters. Do not use the bare word *update* for all three.
2. Which loop counts are runtime hyperparameters versus architectural or learned quantities, and the concrete values used in each reported experiment.
3. Where parameters are shared: across timesteps/cycles, across hierarchy levels, across supervision segments, or not at all. Distinguish “two states” from “two parameter sets.”
4. Which loop is actually enlarged for reported test-time scaling, which inner counts remain fixed, and the resulting total number of inner updates in at least one concrete configuration.
5. At which boundary the model decodes an answer, measures convergence, detaches state, computes a loss, takes an optimizer step, halts, or resets. Two loop schedules with equal raw compute need not be the same protocol when these boundary operations differ.

If a paper overloads words such as *step*, *iteration*, *outer loop*, *cycle*, or
*segment*, flag the collision explicitly and introduce unambiguous report-local
names before presenting results.

### Every figure and table needs its experimental setting

**For each figure or table, find and state the concrete setting behind it.**

| State | What it covers |
|---|---|
| The task | The exact experimental setting being held fixed or changed |
| What the graphics denote | The relevant axes, rows, columns, colors, curves, markers, method names, and panels; expand genuinely nonstandard abbreviations on first use |
| What each number counts | Metric definition, unit, denominator/evaluation population, aggregation over examples/seeds/views, and whether higher or lower is better. Include protocol distinctions that change the meaning of the number, for example frozen probe vs fine-tuning, per-video single-view vs multi-view, or success per episode vs per subgoal |
| One argument-carrying example | The value, the matched baseline, and the absolute or relative change. Translate a decimal such as `0.90` into a count only when the denominator is actually known |
| What it supports | What the experiment supports and what it does not. Separate causal ablations from cross-paper or unmatched comparisons |

If labels are unreadable at report scale, crop or enlarge the relevant panel,
transcribe its values into searchable HTML, or omit the figure; never make the
reader reverse-engineer a thumbnail.

---

## Chapter 3 — Citation Count And Age

### What to write

**Every report carries a dated, attributed citation count together with the
paper's age in the §① metadata block, because a bare count says nothing until it
is divided by age.**

1. The citation count, with the source named and the lookup date: `被引 137 次（Semantic Scholar，@2026-08-13）`. Counts move, so an undated count is unusable later; the indices disagree by an order of magnitude, so an unattributed count is worse.
2. The time since first public release, computed from the v1 date rather than the version you read: `v1 距今 7 个月`. When you read a later version, give both dates so the reader can see the revision gap.

For anything under ~2 years old, add the rate (`≈19 次/月`). When the paper is
younger than ~3 months, say plainly that the count carries no signal yet rather
than presenting it as evidence. Citation count is metadata, not evidence: it may
not appear in the critique or the assessment of the method, and a well-cited paper
does not get an easier reading.

### Where to get the numbers

**Semantic Scholar (S2) is the only usable source; this table was settled by
probing every channel, so do not re-derive it or reach for a source that responds
faster.**

| Channel | Status | Nature |
|---|---|---|
| Semantic Scholar API | 429, clears on retry | The only usable source (§Retry S2 through its shared rate limit) |
| Google Scholar | 403 | Bot-blocked, not throttled: 403 from this machine and from WebFetch's egress, so waiting and switching networks are both pointless. Never try it first |
| OpenReview API (`api` + `api2`) | 403 | WAF challenge. Has no citation counts anyway |
| OpenAlex | 200 | Blacklisted (§Never substitute OpenAlex or Crossref) |
| Crossref | 200 | No arXiv DOIs at all (`10.48550/arXiv.*` → 404). Journals only |
| DBLP | 200 | Never carries citation counts. Also lags on new venues |

### Retry S2 through its shared rate limit

**S2's 429 is a shared unauthenticated pool, not a per-IP ban, so retry to 200 at
~18–20 s spacing, up to ~15 attempts, before declaring it unavailable.** WebFetch
gets the same 429. It clears on its own: measured 7×429 then 200 at ~2.5 min of
20 s spacing, with later queries landing on attempts 6 and 4.

```bash
s2get () { for i in $(seq 1 15); do
    c=$(curl -s -m 25 -o s2.json -w "%{http_code}" "$1")
    [ "$c" = "200" ] && { cat s2.json; return 0; }; sleep 18
  done; echo "FAILED, last HTTP:$c"; }

# 1. by arXiv id when the paper has one — exact, never mis-resolves
s2get "https://api.semanticscholar.org/graph/v1/paper/arXiv:<id>?fields=title,citationCount,influentialCitationCount,referenceCount,year,publicationDate,venue,authors"
# 2. by title only as the fallback for papers with no arXiv id at all
s2get "https://api.semanticscholar.org/graph/v1/paper/search/match?query=<full title>&fields=title,citationCount,year,venue,externalIds"
# then by the paperId it returns, for the full record
s2get "https://api.semanticscholar.org/graph/v1/paper/<paperId>?fields=title,citationCount,influentialCitationCount,referenceCount,year,publicationDate,venue,authors"
```

### Query by arXiv id first

**Query by arXiv id when the paper has one and use the title only when there is
no id, because `search/match` is fuzzy and silently returns a different paper when
the title is short or generic.** "Full-bandwidth transformer" (arXiv:2608.08888)
matched a 2018 cartilage tissue-engineering paper, and the Puffin-World title
returned an empty `{}`; the id lookups gave 2 and 0 citations.

- Whenever you do use `search/match`, compare the returned title/year with the paper before using the number, and say in the report which lookup produced it.
- The title route still matters for papers with no id of any kind: an OpenReview-only ICML 2026 paper (SPT) was reachable only this way.
- Keyword `paper/search` is useless for this (unrelated hits, more 429s).

### A 404 from every lookup is an answer

**A 404 from both the id lookup and `search/match` means the paper is not in S2,
so write 未收录 / not indexed, which is a different statement from "lookup
failed".** On TRM (arXiv:2510.04871) the id lookup returned 404, `search/match` on
the full title returned 404, and a keyword `paper/search` returned ten hits that
were all papers citing it rather than TRM itself. Say which of the three queries
you ran, and do not fill the gap from another index.

### Never substitute OpenAlex or Crossref

**A wrong number is worse than a missing one, and OpenAlex and Crossref return
wrong numbers; their lack of a rate limit is exactly what makes them tempting.**
Measured against S2 the same day: Huginn 2 vs 317, HRM 3 vs 133, because they
mostly miss arXiv→arXiv citations. OpenAlex also fails silently: `search=`
returned InstructGPT as the top hit for Coconut's title and a 2006 statistics
paper for HRM's, and its `works/doi:` record for an arXiv preprint can be
mis-linked to a different title outright.

### When the paper has no identifier

**A very new conference paper can have no arXiv id, no DOI, and no proceedings
page, so stop hunting other indexes and query S2 by title.** PMLR volumes 404 for
a long time after the conference: ICML 2026's v306 was still the only hole in an
otherwise continuous v305/v307 sequence five weeks after the poster session.

- With no identifier there is no hook for any index, so Crossref/OpenAlex/DBLP/web search all legitimately return zero hits.
- S2 crawls PDFs directly and usually has a bare stub record: correct title, authors, and `referenceCount`, but empty `venue`, `year`, and `publicationDate`. Report that stub's count and say it is a stub, so a `0` reads as "real but very fresh" rather than "not indexed".
- For the age, the conference virtual site carries the exact date and is reachable: grep `icml.cc/virtual/<year>/papers.html` for the title to get the poster id, then read the date off `icml.cc/virtual/<year>/poster/<id>` (NeurIPS/ICLR are the same shape). Prefer this over the PDF's production date, which can be a couple of months early.
