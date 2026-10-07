---
name: paper-reading
description: Write a hierarchical paper deep-reading report with clear central messages, complete deeper explanations, and a final Agent comment chapter.
---

# Paper Deep Reading

Owns what a paper deep-reading report contains and how it is written. The HTML
source and the PDF are [harness/skills/paper-reading/references/rendering.md](references/rendering.md); file names and folders under
`readings/` are `readings/README.md`. Reports live in `readings/tutorials/`.

Chapter 1 is what a report is for; Chapter 2 is what goes into it; Chapter 3 is
how to review the report before delivery.

---

## Chapter 1 — What A Report Is For

### Extract the paper's message

**The agent must distill the paper's central messages and organize the report
around them.** Write the body in Simplified Chinese while keeping technical
names and identifiers in English.

Start by identifying what the reader should remember: the problem that matters,
the key insight, and what the paper establishes. Explain what changes relative
to prior approaches and why that change matters. A list of modules, benchmark
scores, or abstract sentences does not explain the contribution.

Read broadly enough to identify the main argument, then organize the explanation
by depth. Give the central mechanism and its strongest evidence prominence.
Preserve the detail needed for a thorough understanding in deeper layers instead
of crowding the opening or deleting it to make the report short.

### Organize by depth

**Make the report hierarchical: start with a concise high-level message, then
progressively unfold a complete explanation for readers who want the details.**
The reader should be able to stop at a chosen depth with a coherent understanding,
or continue without having to reconstruct missing steps from the paper.

| Depth | What the reader gets |
|---|---|
| High-level message | The problem, key insight, main finding, and why it matters, readable on its own |
| Main explanation | How the idea works, what changes from prior approaches, and the decisive evidence, with only the background needed here |
| Detailed explanation | Method steps, equations and derivations where needed, experimental protocols, ablations, secondary results, and relevant qualifications |

These are levels of explanation, not a required set of chapter names or a fixed
number of levels. Use descriptive headings and deeper subsections so the reader
can find a specific detail. A complex mechanism can have its own short overview
followed by a detailed walkthrough. Put extensive technical material after the
main explanation or in clearly linked detail sections before `Agent comment`.

An overview states the takeaway; deeper text adds how, why, evidence, or scope.
Do not repeat the same summary at every level. Keep qualifications that change
the high-level conclusion visible there; defer their technical explanation,
not their existence. Complete information means enough detail to understand the
paper's contributions and evidence, not a verbatim translation of every page.

### Previous reports are not quality standards

**Do not treat previous reports as good reports or use their format and style
as the recommended template.** Their existence does not establish their quality
or the user's approval of their writing choices.

Choose the structure from the current paper and the user's request. Earlier
reports may provide relevant cross-links, but do not inherit their length,
section lists, repeated explanations, or presentation habits. Rendering mechanics
belong to [harness/skills/paper-reading/references/rendering.md](references/rendering.md); they do not determine the report's narrative.

### Write for fast reading

**Make the main message easy to find and give each level the detail its reader
needs.** Assume no prior topic context, but introduce background where
it becomes necessary instead of writing a general textbook introduction.

Use short connected paragraphs for explanations, bullets for parallel points,
and tables for comparisons. Do not force every paragraph into a bold-led bullet.
Explain unfamiliar terms and abbreviations on first use, especially overloaded
words such as *task*, *world model*, or *step*. Preserve the paper's method names.
State shared definitions and experimental settings once.

Keep the upper levels concise without making the full report shallow. A concrete
example or derivation belongs where it helps the reader understand the mechanism.
Move dense result tables and technical explanations to deeper sections. Cut
redundancy and generic praise or criticism, not useful depth. Total length alone
does not determine quality; the reader's path through it matters.

### Explain faithfully and reserve commentary for the end

**The body should explain and synthesize the paper; the final `Agent comment`
chapter holds the agent's own assessment and research suggestions.** Distilling
the paper's message is part of the body, not something to postpone to commentary.

Use the agent's own words to connect the problem, mechanism, and evidence.
Attribute claims accurately without labeling every paragraph by source. Cite the
relevant section, figure, or table where it helps the reader check a key point.
Identify details obtained from official code when they supplement the paper.
Do not invent missing facts or present an inference as the authors' conclusion.
Mention missing information when it affects the explanation or interpretation,
not as a running inventory of everything the paper leaves unspecified.

---

## Chapter 2 — What Goes Into A Report

### The parts in reading order

**Open with the paper's central message, develop the explanation in the order it
needs, and end with `Agent comment`.** The body headings should reflect this
paper's ideas; the table below describes their roles, not a mandatory heading
list to fill out.

| Part | Contents |
|---|---|
| Opening | A short account of the problem, key insight, main finding, and significance; make the contribution concrete |
| Compact metadata | Exact identity and useful links, with citation count and age; keep this from interrupting the explanation |
| Main explanation | Necessary task setup, the key mechanism, and decisive evidence; explain how they support the central message |
| Deeper sections | A fuller account of methods, derivations, protocols, ablations, and results, organized beneath or after the main explanation |
| Agent comment, final chapter | The agent's assessment, substantive limitations or open questions, and useful connections to the user's research |

For the method, first explain the recipe and why the important design choices
matter, then unfold the technical details. Present decisive ablations in the main
explanation and cover the remaining substantive ablations in deeper sections.
Tables can compactly preserve results without narrating every cell. Explain what
each group of experiments establishes and any exceptions that affect the message.
Keep limitations needed to state a result accurately with that result. Put
independent criticism in the final chapter.

### Agent comment

**Use `Agent comment` only as the report's final chapter, with focused judgments
supported by reasons.** It is not a label for the whole report or a recurring
block after each figure or section.

Discuss what is convincing, what remains unresolved, and what is useful to try
or think about next, as relevant to this paper. Distinguish the agent's hypotheses
from established findings. Avoid another summary of the body and generic
limitations that could be attached to any paper.

Connect to the user's research only when there is a concrete mechanism, finding,
or experiment to discuss. Use the current conversation and [harness/skills/experiment-loop/SKILL.md](../experiment-loop/SKILL.md) for
context; when nothing connects, say so in one line. Relevant outside assessments
may inform this chapter, with attribution.

### Metadata and links

**Give the paper's identity exactly, and print only links you have opened.**

- Include the exact title, authors, affiliations, date/version, venue, arXiv id, local PDF, and project/code links in a compact metadata block.
- Preserve complete authorship, with the equal-contribution and corresponding-author markers.
- Include a prominent Demo/链接 block; when the paper has a video demo, link it with a clear 🎬 marker.
- When a kind of link does not exist, such as a project page or a demo, write 无 for it rather than leaving it out.

### Citation count and age

**Report the citation count with its source and lookup date, together with the
paper's age, because a bare count says nothing until it is divided by age.**

- Write `被引 137 次（Semantic Scholar，@2026-08-13）` and `v1 距今 7 个月`. Count the age from the first version, and give both dates when you read a later one.
- Add the rate, such as `≈19 次/月`, for a paper under about 2 years old, and say that the count carries no signal yet for one under about 3 months old.
- The count is metadata, not evidence, so keep it out of the critique.

### Looking up the count

**Take the count from Semantic Scholar only, because the indexes that answer
faster return wrong numbers, and a wrong number is worse than a missing one.**

- Query by arXiv id when the paper has one. With no id, query `search/match` with the full title and compare the returned title and year, because the match is fuzzy and can return a different paper.
- On HTTP 429, retry every 18 to 20 s, up to about 15 times; the unauthenticated pool is shared and clears on its own.
- When both the id and the title return 404, the paper is not indexed: write 未收录, and name the queries you ran.
- Never take a count from Google Scholar, OpenAlex, Crossref, or DBLP; OpenAlex and Crossref mostly miss arXiv-to-arXiv citations.

```
https://api.semanticscholar.org/graph/v1/paper/arXiv:<id>?fields=title,citationCount,publicationDate,venue
https://api.semanticscholar.org/graph/v1/paper/search/match?query=<full title>&fields=title,citationCount,year,venue,externalIds
```

The measurements behind these rules, and the case of a conference paper with no
identifier at all, are in [archive/audits/2026-08-14_citation_sources.md](../../../archive/audits/2026-08-14_citation_sources.md).

### State the setting behind every result

**For each figure or table you show, find the concrete setting that produced it
and state it once, using the items that result needs.** A setting can include:

| Item | What it covers |
|---|---|
| The task | What is held fixed and what is changed |
| What the graphics denote | Axes, rows, columns, colors, curves, markers, method names, and panels, with nonstandard abbreviations expanded |
| What each number counts | Metric, unit, evaluation population, aggregation over examples, seeds, or views, and whether higher or lower is better. Include a protocol difference that changes the meaning of the number, such as frozen probe vs fine-tuning |
| One argument-carrying example | The value, the matched baseline, and the absolute or relative change. Translate a decimal such as `0.90` into a count only when the denominator is actually known |
| What it supports | And what it does not. Separate causal ablations from cross-paper or unmatched comparisons |

- When several tables share a setting, state it once and then name only what differs.
- These items are what to look for, not headings to repeat under every table.
- If labels are unreadable at report scale, crop or enlarge the relevant panel, transcribe its values into searchable HTML, or omit the figure.

### Nested recurrence and test-time scaling

**For recurrent, iterative, hierarchical, or adaptive-compute models, never report
a compact tuple such as `H/L = 3/6` without expanding its operational meaning.**
Give executable nesting or an explicit timeline, and state:

| State | Detail |
|---|---|
| What one update changes | At each level: a latent state, an output proposal, or model parameters. Do not use the bare word *update* for all three |
| Which loop counts are set at run time | Which are architectural or learned instead, and the concrete values used in each reported experiment |
| Where parameters are shared | Across timesteps or cycles, across hierarchy levels, across supervision segments, or not at all. Two states are not two parameter sets |
| Which loop grows at test time | Which inner counts remain fixed, and the total number of inner updates in at least one concrete configuration |
| Where each boundary sits | Where the model decodes an answer, measures convergence, detaches state, computes a loss, takes an optimizer step, halts, or resets. Two schedules with equal raw compute are different protocols when these differ |

If a paper overloads words such as *step*, *iteration*, *outer loop*, *cycle*, or
*segment*, flag the collision explicitly and introduce unambiguous report-local
names before presenting results.

### What others say about the paper

**Include later work or public discussion when it changes the understanding of
the paper, and attribute each statement to its source.**

- Look for relevant follow-up papers, reproductions, public reviews, and issues on the official repository; select substantive evidence rather than compiling a survey.
- For a well-known paper, name the actual follow-up work, not only the directions it could lead to.
- If no relevant follow-up or discussion is found, say so briefly without assuming none exists.
- Put the agent's assessment of this evidence in the final `Agent comment` chapter.

### Cross-links to sibling reports

**Link another report in `tutorials/` only at the sentence whose claim genuinely
touches it.**

- Use a plain `<a href="<slug>_deep_reading.html">…</a>` and one clause saying what the reader gets by following it: a shared mechanism, a contradicting measurement, or the same idea on a different axis.
- Do not collect links into a "related work" appendix.
- Before delivering, confirm every such href resolves to a file that exists.

---

## Chapter 3 — Review Before Delivery

### Check the message and the scope

**Review whether the report makes the paper understandable, not whether it fills
every possible section.**

| Check | Revision if it fails |
|---|---|
| Can the reader state the key insight and finding after the opening? | Replace topic labels and vague claims with the paper's actual message |
| Does the body explain how the method works and why the evidence matters? | Add the missing mechanism or decisive comparison, not more result listings |
| Can the reader stop at the overview or choose to dive deeper? | Separate levels and add descriptive navigation; move dense detail out of the overview |
| Can a reader find the full explanation of methods and evidence? | Restore missing steps, substantive ablations, protocols, or qualifications in deeper sections |
| Does each level add information? | Replace repeated summaries with explanation, evidence, or detail; remove tangents |
| Are terms, numbers, and comparisons interpretable? | Supply the necessary definition, setting, metric, unit, direction, or baseline where first needed |
| Is information repeated across sections or under every table? | Keep one explanation and refer back only when necessary |
| Was the structure chosen for this paper? | Remove sections inherited merely from earlier reports |
| Is `Agent comment` the final chapter and distinct from faithful explanation? | Move independent assessments there and remove repeated summaries |

### Keep the task a reading report

**Do not turn paper reading into an experimental audit or reproduction unless
the user requests it.** Check the sources needed to explain the paper accurately.
Old reports and batch briefs do not add content requirements to this guide;
use a brief for its task-specific paths and tools, subject to the user's request.
