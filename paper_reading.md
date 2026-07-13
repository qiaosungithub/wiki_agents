# Paper Deep Reading

Deep-reading reports live in
`readings/vision-related/tutorials/`, are registered in that directory's
`index.html`, and use its established HTML template. Write the body in Simplified
Chinese while keeping technical names and identifiers in English.

## Required Story

A report should let a reader understand the paper without prior topic context:

1. Exact title, authors, affiliations, date/version, venue, arXiv id, local PDF,
   and project/code links.
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

## Assets And Rendering

- Prefer figures from the arXiv source package; rasterize vector PDFs and resize
  very large images before embedding them under `assets/<slug>/`.
- Rebuild LaTeX tables as searchable HTML rather than screenshots.
- If images are embedded, also render a same-basename PDF. Use the existing print
  override, set a writable `XDG_CACHE_HOME`, pass the tutorials directory as
  WeasyPrint's base URL, and avoid CSS Grid in the print copy. These constraints
  prevent font-cache hangs, missing relative assets, and pathological layout
  time.
- Keep the browser HTML as the canonical report; print-only transformations
  belong in a temporary copy.

Exact extraction and rendering snippets from prior work are retained under
`archive/details/paper_reading.md` for troubleshooting only.
