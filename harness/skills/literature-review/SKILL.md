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

**Only papers that pass screening count. A paper whose results do not hold up is ignored completely:
it is not cited, its numbers are not used, and it does not count as prior work even when its idea is
the same as ours.** This is an operator rule. Low-quality papers are common enough that an unscreened
review is mostly noise: the first screening (47 papers on looped models and fast weights) discarded 7,
three of them well-known papers whose baseline rows were copied from other papers despite a different
stated training setup.

- Overlap with our idea is recorded separately and never changes a verdict. A discarded paper that
  "already did our idea" does not make the idea taken.
- A discarded paper's released model or code can still be used as an artifact. Measurements of that
  artifact made by a kept paper count; the discarded paper's own numbers, including its sub-results,
  do not.
- A paper we could not read in full is UNVERIFIED and is treated as discarded until read.

## Procedure

1. **Collect candidates.** Use the arXiv API through `web_fetch`
   (`http://export.arxiv.org/api/query?search_query=...`, title-restricted queries such as
   `ti:looped AND abs:KV` keep the hit list relevant); `web_search` can fail with a permission error.
   Follow citations in both directions from the strongest kept papers, and add the topic's must-cite
   precedents listed on its research page.
2. **Screen one paper at a time from the full text** (`https://arxiv.org/html/<id>`, else the PDF),
   never from the abstract. Write the headline claim with its number, find the table that is supposed
   to support it, run every check below, then give a verdict.
3. **Fan out above about six papers.** One read-only screener per 5 to 7 papers, all reading one
   shared rubric file and each writing one output file in the same per-paper format. The parent
   re-checks every DISCARD reason and every large headline it intends to rely on before using it.
4. **Report kept papers first,** each with its caveat inside the sentence that cites it, and the
   claims of that paper that must not be cited. Discarded papers appear only in a short ignored list
   with a one-line reason.
5. **Record the result** on the topic's research page (id, verdict, one-line reason, what to use) and
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

## Verdicts

**A paper is judged on whether its results hold, not on whether we like the idea.**

| Verdict | When | How a review uses it |
|---|---|---|
| KEEP | Every check PASS, or only minor CONCERNs | Cite and build on |
| KEEP-CAVEAT, strength 1 to 3 | Results hold within a stated limit (scale, seeds, one task family), or a secondary claim fails while the headline holds | Cite with the caveat in the same sentence; list the claims not to cite. Strength 3 is near KEEP, strength 1 barely passes |
| DISCARD | A FAIL on C1, C2 or C3 that the headline depends on; any C6 FAIL that touches the headline; C10 junk; every headline gain within noise (C4) with nothing else in the paper standing; or two or more FAILs elsewhere | Ignore completely |
| UNVERIFIED | Full text not read | Treat as DISCARD |

## Red Flags That Decided Real Verdicts

**The checks that caught bad papers were mechanical comparisons, not impressions.**

| Flag | How it was found |
|---|---|
| Baseline rows copied from another paper while the stated setup differs | Cell-by-cell comparison with the suspected source table: identical cells plus a consistent shift in the paper's favour |
| Printed average that does not match its own columns, propagated into later papers | Recomputing every aggregate with a script |
| In-house baseline far below the baseline's own published number | Looking up the baseline's technical report |
| A method-only optimizer trick worth as much as the reported gain | The paper's own trick ablation, read against the main table |
| Gains within single-seed noise on an aggregate that counts benchmarks twice | Computing the SE and re-deriving the aggregate |
| A headline that exists only as a plot, with the protocol unstated | Searching for the table behind the claim and finding none |
