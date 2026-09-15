# Paper Report Rendering

Owns the HTML and PDF of a paper deep-reading report. What a report must contain
is `paper_reading.md`. The PDF is produced with WeasyPrint, which runs no page
JavaScript.

Chapter 1 is the HTML source and its line structure; Chapter 2 is figures, the
PDF, and inspection.

---

## Chapter 1 — The HTML Source

### The browser HTML is the canonical report

**Keep the browser HTML as the canonical report, and make every print-only change
in a temporary copy (Chapter 2).** Build a new report on the established HTML
template of `readings/tutorials/` rather than a new design. A bilingual report is
two HTML files with matching section ids, each linking to the other.

### Do not rely on source newlines

**Do not rely on literal source newlines inside an ordinary
`<div class="formula">`, because at the default `white-space: normal` HTML
collapses newlines and runs of spaces into one space.** A browser can look right
only because it wraps at the viewport edge. The A4 print layout is narrower and
uses different font metrics, so WeasyPrint can join intended lines and break
equations at semantically wrong positions. `overflow: auto` is not a print fix,
because a PDF has no horizontal scrollbar; content wraps badly or is clipped.

### Encode each kind of content explicitly

**Choose the encoding by the kind of content, and keep manual semantic breaks as
the primary layout mechanism.**

| Content | Encoding |
|---|---|
| Equations and short derivations | One block element per semantic line, such as `<div class="eq-line">...</div>`, or explicit `<br>` elements. Break before or after a meaningful operator (`=`, `+`, an implication, or a condition), and indent continuation lines deliberately, because source indentation does not survive normal whitespace handling |
| Code or pseudocode whose indentation matters | `<pre class="formula">...</pre>` with `white-space: pre-wrap`. Escape `<`, `>`, and `&` inside it, and avoid a nested inline `<code>` style unless its background and padding are reset for the block |
| Every formula block | A print-safe fallback: `overflow-wrap: anywhere`, `word-break: normal`, and `overflow: visible`, with a print font size and line height that fit the A4 content width. The fallback must not decide where a long equation breaks |
| A long algorithm or derivation | Smaller logical blocks. Use `break-inside: avoid` only for a block known to fit on one page, because a page-sized unbreakable box creates blank pages or overflow |

A robust plain-HTML pattern is:

```html
<div class="formula">
  <div class="eq-line">z_t = AddNoise(x_0, epsilon, t)</div>
  <div class="eq-line">z_0:T = Rollout(v_theta; z_T, c)</div>
  <div class="eq-line indent">therefore: query the teacher at z_t</div>
</div>
```

### Math must render without JavaScript

**Never depend on client-side MathJax or KaTeX for the PDF, because WeasyPrint
runs no page JavaScript.** Use already-rendered static markup or SVG, MathML known
to work in the renderer, or print-safe HTML text.

---

## Chapter 2 — Figures, The PDF, And Inspection

### Size a figure by its information density

**Size each figure by its information density in the rendered PDF, not by
defaulting every image to `width: 100%`.** A simple single-curve plot, small
architecture sketch, or qualitative example normally takes half a page or less;
reserve near-full-page figures for dense multi-panel evidence whose labels would
otherwise be unreadable.

- Use figure-specific print classes or `max-width` / `max-height` constraints to balance readability, surrounding explanation, whitespace, and page count.
- A legible image that fills a whole page is a layout failure, and so is a dense plot shrunk until its axes or legend are unreadable. Crop or split its panels, or transcribe key values into HTML.
- Prefer figures from the arXiv source package. Rasterize vector PDFs and resize very large images before embedding them under `assets/<slug>/`.
- Rebuild LaTeX tables as searchable HTML, not screenshots.

### Render a same-basename PDF through the shared print override

**If images are embedded, also render a same-basename PDF from a temporary print
copy.**

- Use the existing print override, set a writable `XDG_CACHE_HOME`, pass the tutorials directory as WeasyPrint's base URL, and avoid CSS Grid in the print copy. These prevent font-cache hangs, missing relative assets, and pathological layout time.
- `tutorials/_pdf_print_override.html` is shared by every report, so read it fresh at render time and never hand-patch it per report.
- Its `.grid > .box` flex-basis is tuned against a measured WeasyPrint threshold. WeasyPrint treats percentages as the content box, so too large a basis silently stacks every box full-width; the file's comment records the measurement.
- If you must change the override, re-measure on a real report, not a toy page, and re-render every report that already shipped.

### Inspect the real PDF before delivery

**Browser HTML inspection is not sufficient, so render the actual PDF and look at
every formula and pseudocode page at readable resolution, plus a contact sheet of
the whole document.** `pdftotext -layout` is a useful secondary check but does not
replace looking.

| Check | Failure it catches |
|---|---|
| Line count and indentation | Intended lines joined, or their grouping lost |
| Tokens and subscripts | Clipping |
| Line breaks | A line broken at an arbitrary symbol |
| Page breaks | A block split across pages, or an avoidable blank or figure-only page |
| Figure footprint | A figure whose size does not match the evidence it carries |

Exact extraction and rendering snippets from earlier work are kept in
`archive/details/paper_reading.md` for troubleshooting only.
