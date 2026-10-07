# Audit Snapshot: Citation Sources (2026-08-14)

Dated evidence behind `paper_reading.md` §Looking up the count. Every channel was
probed on 2026-08-14, and the rule to query by arXiv id first was added on
2026-09-11. Below is the citation chapter of `paper_reading.md` as it stood before
that page was shortened; re-verify a channel's status live before relying on it.

## The text as it stood

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
