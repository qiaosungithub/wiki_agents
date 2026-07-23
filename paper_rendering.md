# Paper Report Rendering

Read this when laying out, rendering, or debugging the HTML/PDF of a paper
deep-reading report. Report content requirements are in `paper_reading.md`.
The PDF is produced with WeasyPrint, which runs no page JavaScript.

## Formula, Derivation, And Pseudocode Line Breaks

Do not rely on literal source newlines inside an ordinary
`<div class="formula">`. With the default `white-space: normal`, HTML collapses
newlines and runs of spaces into one space. A browser may appear to separate the
content only because it wraps at the viewport edge; the A4 print layout is
narrower and uses different font metrics, so WeasyPrint can concatenate intended
lines and then break equations at arbitrary, semantically wrong positions.
`overflow: auto` is not a print fix because a PDF has no horizontal scrollbar;
content may instead wrap badly or be clipped.

Encode line structure explicitly according to the content:

1. For equations and short derivations, use one block element per semantic line,
   such as `<div class="eq-line">...</div>`, or explicit `<br>` elements. Break
   before or after meaningful operators (`=`, `+`, an implication, or a condition),
   and give continuation lines a deliberate indent. Do not expect indentation in
   the HTML source to survive normal whitespace handling.
2. For code or pseudocode whose indentation is meaningful, use
   `<pre class="formula">...</pre>` and set `white-space: pre-wrap`. Escape `<`,
   `>`, and `&` inside it. Avoid a nested inline `<code>` style unless its
   background and padding are explicitly reset for the block.
3. Give formula blocks a print-safe fallback: `overflow-wrap: anywhere`,
   `word-break: normal`, and `overflow: visible`; choose a print font size and
   line height that fit the A4 content width. Manual semantic breaks remain the
   primary layout mechanism—the fallback must not be the thing deciding where a
   long equation breaks.
4. Use `break-inside: avoid` only for a block known to fit on one page. Split a
   long algorithm or derivation into smaller logical blocks instead of forcing a
   page-sized unbreakable box, which creates blank pages or overflow.
5. Do not depend on client-side MathJax/KaTeX execution for the PDF: WeasyPrint
   does not run page JavaScript. Use already-rendered static markup/SVG, MathML
   known to work in the chosen renderer, or print-safe HTML text.

A robust plain-HTML pattern is:

```html
<div class="formula">
  <div class="eq-line">z_t = AddNoise(x_0, epsilon, t)</div>
  <div class="eq-line">z_0:T = Rollout(v_theta; z_T, c)</div>
  <div class="eq-line indent">therefore: query the teacher at z_t</div>
</div>
```

Before delivery, render the actual PDF and inspect every formula/pseudocode page
at readable resolution. Check that the intended line count survived, indentation
still carries the right grouping, no token or subscript is clipped, no line is
broken at an arbitrary symbol, and the block is not split across pages. Browser
HTML inspection alone is insufficient; `pdftotext -layout` is a useful secondary
check but does not replace visual inspection.

## Assets And Rendering

- Prefer figures from the arXiv source package; rasterize vector PDFs and resize
  very large images before embedding them under `assets/<slug>/`.
- Size each figure according to its information density in the **rendered PDF**,
  rather than defaulting every image to `width: 100%`. A simple single-curve
  plot, small architecture sketch, or qualitative example should normally use
  roughly half a page or less. Reserve near-full-page figures for genuinely
  dense multi-panel evidence whose labels would otherwise be unreadable.
- Use figure-specific print classes or `max-width` / `max-height` constraints to
  balance readability, surrounding explanation, whitespace, and page count.
  An image that is technically legible but unnecessarily occupies an entire
  page is a layout failure. Conversely, do not shrink a dense plot until its
  axes or legend become unreadable; crop/split panels or transcribe key values
  into HTML instead.
- Rebuild LaTeX tables as searchable HTML rather than screenshots.
- If images are embedded, also render a same-basename PDF. Use the existing print
  override, set a writable `XDG_CACHE_HOME`, pass the tutorials directory as
  WeasyPrint's base URL, and avoid CSS Grid in the print copy. These constraints
  prevent font-cache hangs, missing relative assets, and pathological layout
  time.
- Keep the browser HTML as the canonical report; print-only transformations
  belong in a temporary copy.
- Inspect both a contact sheet and the relevant pages at readable resolution.
  Check not only clipping and font size, but also whether each figure's visual
  footprint is proportional to the evidence it carries and whether avoidable
  blank or figure-only pages were introduced.

Exact extraction and rendering snippets from prior work are retained under
`archive/details/paper_reading.md` for troubleshooting only.
