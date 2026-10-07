# Paper Report Rendering

Owns the HTML source and the PDF of a paper deep-reading report. What a report
contains is [harness/skills/paper-reading/SKILL.md](../SKILL.md); file names and folders are `readings/README.md`.
The PDF is produced with WeasyPrint, which runs no page JavaScript.

Chapter 1 is the HTML source; Chapter 2 is rendering and inspecting the PDF;
Chapter 3 is what goes wrong in print.

---

## Chapter 1 — The HTML Source

### The browser HTML is the canonical report

**Keep the browser HTML as the canonical report, and make every print-only change
in a temporary copy (Chapter 2).**

- Choose HTML structure and visual hierarchy for the current paper. Do not copy the most recent report as a style or content template; reuse only rendering mechanics that have been checked for the current output.
- Keep exactly one `<style>` block and no `<script>`, because the print step inserts its override after that one block and WeasyPrint runs no script.
- A bilingual report is two HTML files with matching section ids, each linking to the other.

### Encode each kind of content explicitly

**Choose the encoding by the kind of content, because the A4 page is narrower
than a browser window and a PDF has no scrollbar.**

| Content | Encoding |
|---|---|
| Math | TeX rendered to inline SVG when the report is built (§Render math to SVG before printing). Plain `<sub>` and `<sup>` are enough for a trivial inline symbol |
| Code or pseudocode whose indentation matters | `<pre class="formula">...</pre>` with `white-space: pre-wrap`. Escape `<`, `>`, and `&` inside it, and avoid a nested inline `<code>` style unless its background and padding are reset for the block |
| A table | Searchable HTML rebuilt from the LaTeX source, not a screenshot, with the header row in `<thead>` and the other rows in `<tbody>` |
| A long algorithm or derivation | Smaller logical blocks. Use `break-inside: avoid` only for a block known to fit on one page, because a page-sized unbreakable box creates blank pages or overflow |

### Render math to SVG before printing

**Write math as real TeX and render it to inline SVG when the report is built,
because plain-text formulas read badly and the PDF cannot depend on client-side
MathJax or KaTeX.**

- Render with the SVG output of `mathjax-full` under Node, and put each SVG directly in the HTML, not in a separate file.
- Set `fontCache: 'none'`, so that every SVG carries its own glyph paths and shares no id with another SVG.

### Size a figure by its information density

**Size each figure by its information density in the rendered PDF, not by
defaulting every image to `width: 100%`.** A simple single-curve plot, small
architecture sketch, or qualitative example normally takes half a page or less;
reserve near-full-page figures for dense multi-panel evidence whose labels would
otherwise be unreadable.

- Use figure-specific print classes or `max-width` / `max-height` constraints to balance readability, surrounding explanation, whitespace, and page count.
- A legible image that fills a whole page is a layout failure, and so is a dense plot shrunk until its axes or legend are unreadable. Crop or split its panels, or transcribe key values into HTML.
- Prefer figures from the arXiv source package. Rasterize vector PDFs and resize very large images before embedding them under `assets/<slug>/`.
- Keep the caption short, and place the explanation at the appropriate reading depth. Use prose or a list according to the argument.

---

## Chapter 2 — Rendering And Inspecting The PDF

### Render a same-basename PDF through the shared print override

**Every report ships with a PDF of the same base name, rendered from a temporary
print copy that carries the shared print override.**

1. Read `tutorials/_pdf_print_override.html` fresh at render time and take its last `<style>` block. The file's header comment also contains the text `<style>`, so check that the block you took contains `@page`.
2. Write a temporary copy of the report with that block inserted after the report's `</style>`.
3. Set a writable `XDG_CACHE_HOME`, and render the copy with the tutorials directory as WeasyPrint's base URL.

```bash
export XDG_CACHE_HOME=<writable dir>
weasyprint --base-url readings/tutorials/ <temp copy>.html readings/tutorials/<slug>_deep_reading.pdf
```

- The override is shared by every report, so never hand-patch it per report.
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

---

## Chapter 3 — What Goes Wrong In Print

**Match the symptom you see against this table before changing any CSS.**

| Symptom | Cause | Fix |
|---|---|---|
| WeasyPrint sits at 0% CPU and never finishes | fontconfig has no writable cache directory | Set `XDG_CACHE_HOME` |
| The render takes many minutes | The override was not applied, so CSS Grid reached WeasyPrint; usually the `<style>` text in the override's comment was taken for the block | Take the last `<style>` block and check that it contains `@page` |
| The PDF is tiny and has no images | Relative `assets/` paths resolved against the folder of the temporary copy | Pass the tutorials directory as the base URL |
| One figure makes the render crawl | The image is thousands of pixels wide, however small its file | Resize it to about 1800 pixels wide or less |
| The boxes of a `.grid` stack at full width | WeasyPrint treats a percentage flex-basis as the content box and adds the padding on top, so the row overflows | Keep the override's `.grid > .box` basis; the file's comment records the measured threshold |
| An inline fraction is blank | The SVGs share ids, because a font cache numbers them the same way in every SVG | Render with `fontCache: 'none'` |
| A table header sits alone at the bottom of a page | WeasyPrint keeps a header with its table body only when the header is a `<thead>` | Put the header row in `<thead>` |
| A figure jumps to the next page and leaves a gap | A long caption makes the unbreakable figure too tall for the space left | Keep the caption short |
| The lines of a text block are joined | At the default `white-space: normal`, HTML collapses newlines and runs of spaces into one space | Use a `<pre>`, or one block element per line |
| A `<pre>` line wraps or is cut off | A printed line holds about 78 columns, counting a CJK character as 2, and `overflow: auto` cannot help because a PDF has no horizontal scrollbar | Shorten the line |
| A numbered list restarts at 1 | WeasyPrint ignores `<ol start=N>` | Keep the items in one `<ol>` |

Exact extraction and rendering snippets from earlier work are kept in
[archive/details/paper_reading.md](../../../../archive/details/paper_reading.md) for troubleshooting only.
