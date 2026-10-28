---
name: literature-review
description: Survey prior work for a research idea and screen every paper for result robustness before it may shape a plan, a novelty judgment, or a citation; use for any literature review, related-work survey, or "has this been done?" check.
---

# Literature Review With Paper Screening

This skill owns how to find papers, screen each one for whether its results hold up, and report a
review. Screened paper lists live on the research pages under [knowledge/research/](../../../knowledge/research/README.md),
for example [looped_kv_literature.md](../../../knowledge/research/looped_kv_literature.md). A Chinese
deep-reading report of a single paper is the [paper-reading skill](../paper-reading/SKILL.md).

## The Rule

**Only papers that pass screening count, and screening asks two questions: can the evidence be
trusted, and is the paper worth our attention. A tier D paper (untrustworthy evidence) is ignored
completely, even when its idea is the same as ours; a tier C paper (correct but low value) stays out
of the main review.** This is an operator rule. Low-quality papers are now common, and in a hot topic
most new papers are less than a month old: of 20 looped-LM KV papers screened, 12 were under two
months old and none of those reached tier A.

- Overlap with our idea is recorded separately and never changes a tier. A discarded paper that
  "already did our idea" does not make the idea taken.
- A discarded paper's released model or code can still be used as an artifact. Measurements of that
  artifact made by a kept paper count; the discarded paper's own numbers, including its sub-results,
  do not.
- A paper we could not read in full is UNVERIFIED and is treated as tier D until read.

## Calibration: Integrity Is Not Overclaim, Consistency Is Not Value

**Discard a paper for untrustworthy evidence, never for overselling a comparison to outside models;
and never keep a paper only because its tables are internally consistent.** The first screening got
both wrong. It discarded Ouro, a well-known paper whose released checkpoints most later looped-LM
papers test on, because its in-house re-evaluation of other LLMs ran below their published numbers.
At the same time it kept every recent paper whose tables added up, although a carefully written (or
LLM-written) paper can be consistent and still add nothing.

| Finding | Treatment |
|---|---|
| Baseline rows copied from another paper while a different setup is stated; shifted copies; a stated protocol the paper's own numbers contradict | Tier D |
| The headline rests on a confound the paper created (a trick given only to the method that is worth the whole gain) | Tier D |
| Overclaim against external models (in-house re-evaluation under a weaker protocol, "matches a 12B model"), when the paper's own artifact or core result is real and independently re-measured | Caveat; list the claims not to cite |
| Reusing published baseline numbers under the same setup, with attribution | Normal practice, no penalty |
| An arithmetic slip in a baseline row that does not carry the headline | Caveat |
| Gains within noise on a single seed | Weak evidence: lowers the tier (usually C), not an integrity failure |

## Value And Maturity

**For every paper also record its age, its maturity signals and the size of its contribution,
checking each signal rather than guessing.**

- **Age.** The arXiv id `yymm` gives the month. A paper under two months old has had no time for
  independent use, so it cannot be tier A.
- **Maturity signals.** Peer-reviewed venue; code or checkpoints released and resolving (check the
  links; a repository commit can appear after the paper); independent adoption (other papers using
  its model, method or numbers: grep the related papers' full texts and run an arXiv API abstract
  search for its name); independent replication or contradiction; revised arXiv versions. Semantic
  Scholar citation counts are often rate-limited and are only a weak signal anyway.
- **Contribution.** New method, measurement, system or theory. Ask whether it is a reusable idea or
  finding, or an incremental tweak measured against in-house baselines. An inference engine or a
  quantization scheme can be correct and still be low value for a research question.
- **Independence.** Agreement between papers that share authors is one piece of evidence, not two.

## Procedure

1. **Collect candidates.** Use the arXiv API through `web_fetch`
   (`http://export.arxiv.org/api/query?search_query=...`, title-restricted queries such as
   `ti:looped AND abs:KV` keep the hit list relevant); `web_search` can fail with a permission error.
   Follow citations in both directions from the strongest kept papers, and add the topic's must-cite
   precedents listed on its research page.
2. **Screen one paper at a time from the full text** (`https://arxiv.org/html/<id>`, else the PDF),
   never from the abstract. Write the headline claim with its number, find the table that is supposed
   to support it, run every check below, record value and maturity, then give a tier.
3. **Fan out above about six papers.** One read-only screener per 5 to 7 papers, all reading one
   shared rubric file and each writing one output file in the same per-paper format. The parent
   re-checks every tier D reason, and every large headline it intends to rely on, from the primary
   source before using it, and sanity-checks the tiers against field knowledge: a well-known paper
   in tier D, or a stack of one-month-old papers in tier A or B, means the calibration is off.
4. **Report tier A first, then tier B flagged as unvetted concurrent work,** each with its caveat
   inside the sentence that cites it and the claims of that paper that must not be cited. Tier C and
   D papers appear only in an appendix with a one-line reason.
5. **Record the result** on the topic's research page (id, tier, one-line reason, what to use) and
   keep the full per-paper audit in a durable file that page points to, so the next review starts from
   it instead of re-screening.

## The Checks

**Every check gets PASS, CONCERN, FAIL or N/A, with one line of evidence that names the table,
figure or section.** N/A is for checks that do not apply, such as baselines in a pure theory paper.

| # | Check | FAIL looks like | How to test it |
|---|---|---|---|
| C1 | Claim matches evidence | Headline backed by no table; claim broader than the tested scale, tasks or models; headline exists only in a plot; abstract contradicts a limitation the appendix admits | Write the claim with its number and find its table; read the appendix limitations |
| C2a | Baseline strength | Obvious strongest baseline missing; the authors' own strongest prior model left out | List the baselines a reviewer would expect |
| C2b | Recipe parity | A trick (optimizer, layerwise LR, normalization, loss, extra fine-tuning) given only to the method; the method got a sweep and the baseline did not; one LR shared across different architectures | Look for the baseline-plus-trick ablation; if the trick alone is worth the gain, FAIL |
| C2c | Baseline provenance | Baseline rows copied from another paper whose setup differs from the one stated; baseline numbers far below the baseline's own published or independently re-measured numbers | Compare suspicious rows cell by cell with the source table; check the baseline's own report |
| C3a | Matched training budget | The gain disappears once parameters, tokens, training FLOPs or state size are matched | Find the matched comparison or compute the budgets |
| C3b | Matched inference budget, realized savings | The gain needs more inference compute than the baseline; a claimed saving (KV bytes, FLOPs) never shows up as latency or throughput, or is measured on decode only | Compare claimed savings with measured wall-clock |
| C4 | Noise | Gain below about twice its standard error; single seed on a noisy metric; seed variance and evaluation noise conflated | Compute the binomial SE `sqrt(p(1-p)/n)`: GSM8K (n = 1319) is about 1.3 pt at 50% accuracy; a 7-task commonsense average near 1B parameters is about 0.5 pt |
| C5 | Selective reporting, test-set tuning | Only winning metrics, tasks or checkpoints; benchmark subsets change between tables; hyperparameters chosen on the reported test sets; a self-defined aggregate or one that counts a benchmark twice | Compare the task lists across tables |
| C6 | Internal consistency | Printed averages that do not match their own per-task columns; captions contradicted by appendix tables; one configuration with different numbers in different tables; impossible numbers | Recompute every average with a script |
| C7 | Train/test mismatch | Training computes something different from inference (a parallel approximation of a sequential computation) and the gap is never measured | Find the measured gap, or note its absence |
| C8 | Reproducibility | No code and too few details to reproduce; code or results promised "in the next version" that never arrived | Check the code link resolves and the arXiv version history |
| C9 | Prior-work honesty | An existing method renamed without citation; the closest prior work missing | A FAIL limits the paper's novelty claim; on its own it does not discard results that hold |
| C10 | Substance | Invented metrics with no validation; theory the experiments never use; theorem conditions far from the tested regime; references that do not exist | Judge content, not prose: LLM-like writing alone is not a FAIL |

Record two more fields that do not score: **independence** (shared authors or affiliation with the
papers it corroborates; agreement among papers by the same group is not independent evidence) and
**independent replication** (a later independent paper reproduced it or failed to, and what you
searched).

## Tiers

**A tier combines trust in the evidence with value and maturity; a paper is never tiered on whether
we like its idea.**

| Tier | When | How a review uses it |
|---|---|---|
| A, established | Results hold (no headline-carrying FAIL) and the paper is mature: a venue or released artifacts, plus independent use or replication | Core evidence; cite with its caveats and its do-not-cite claims |
| B, credible recent | Results hold and the paper is directly relevant with decent evidence, but it is too new or unreplicated to rely on | Included, flagged "unvetted concurrent work" in the same sentence; conclusions resting on it get lower confidence |
| C, low value | Not untrustworthy, but incremental, weakly evidenced (gains within noise, in-house baselines only), or not informative for the question | Appendix only, one line |
| D, discard | Untrustworthy evidence per the calibration table: fabrication-like copies, a stated protocol contradicted by the numbers, a headline resting on a self-made confound, or no evidence | Ignored completely, even if the idea overlaps ours |
| UNVERIFIED | Full text not read | Treat as D until read |

## Red Flags That Decided Real Tiers

**The checks that caught bad papers were mechanical comparisons, not impressions.**

| Flag | How it was found |
|---|---|
| Baseline rows copied from another paper while the stated setup differs | Cell-by-cell comparison with the suspected source table: identical cells plus a consistent shift in the paper's favour |
| Printed average that does not match its own columns, propagated into later papers | Recomputing every aggregate with a script |
| In-house baseline far below the baseline's own published number | Looking up the baseline's technical report |
| A method-only optimizer trick worth as much as the reported gain | The paper's own trick ablation, read against the main table |
| Gains within single-seed noise on an aggregate that counts benchmarks twice | Computing the SE and re-deriving the aggregate |
| A headline that exists only as a plot, with the protocol unstated | Searching for the table behind the claim and finding none |
