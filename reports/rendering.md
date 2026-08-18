# Paper Report Rendering

Read this when laying out, rendering, or debugging the HTML/PDF of a paper
deep-reading report; content requirements are `paper_reading.md`. **The PDF is
produced with WeasyPrint, which runs no page JavaScript**, so never depend on
client-side MathJax/KaTeX — use already-rendered static markup/SVG, MathML known
to work in the renderer, or print-safe HTML text.

## Use The CLIPA Synthesis Browser Shell as reference

**Unless the user explicitly asks for another design, every new report uses the
browser-first shell in
`../../readings/vision-related/tutorials/clipa_followups_synthesis_report.html`.**
Copy its complete inline CSS rather than substituting another `readings` style
or extracting a new design system.

The shell is a gradient `.header` with a monospace `.kicker`, large `h1`,
`.subtitle`, pill metadata, and plain `.nav` links. The body is a centered
two-column `main`: an `article.content` of warm-paper `.card` sections plus a
290-pixel sticky `.toc` placed after the article. Inside cards, reuse its
`.lead`, `.grid > .box`, `.note`, `.warn`, `.lesson`, `.formula`,
`table.metric`, `.diagram`, `.caption`, and `.tag` components. Preserve the
980-pixel single-column responsive breakpoint, rounded borders, shadows,
sans-serif typography, colors, and inline-CSS packaging. Bilingual reports are
separate HTML files with matching section IDs and reciprocal links in `.nav`.

## Encode Line Structure Explicitly

**Do not rely on literal source newlines inside an ordinary
`<div class="formula">`**: at the default `white-space: normal` HTML collapses
newlines and runs of spaces into one space. A browser may look right only
because it wraps at the viewport edge; the narrower A4 print layout with
different font metrics lets WeasyPrint concatenate intended lines and then break
equations at semantically wrong positions. `overflow: auto` is not a print fix
either — a PDF has no horizontal scrollbar, so content wraps badly or is clipped.

| Content | Encoding |
|---|---|
| Equations, short derivations | **One block element per semantic line** (`<div class="eq-line">`) or explicit `<br>`. Break before or after a meaningful operator (`=`, `+`, an implication, a condition), and indent continuation lines deliberately — source indentation does not survive normal whitespace handling. |
| Code, pseudocode with meaningful indentation | **`<pre class="formula">` with `white-space: pre-wrap`.** Escape `<`, `>`, `&` inside it; avoid a nested inline `<code>` style unless its background and padding are explicitly reset for the block. |
| Any formula block | **A print-safe fallback** — `overflow-wrap: anywhere`, `word-break: normal`, `overflow: visible`, and a print font size and line height fitting the A4 content width. Manual semantic breaks stay primary; the fallback must not decide where a long equation breaks. |
| A long algorithm or derivation | Split into smaller logical blocks. **Use `break-inside: avoid` only for a block known to fit one page** — a page-sized unbreakable box creates blank pages or overflow. |

```html
<div class="formula">
  <div class="eq-line">z_t = AddNoise(x_0, epsilon, t)</div>
  <div class="eq-line">z_0:T = Rollout(v_theta; z_T, c)</div>
  <div class="eq-line indent">therefore: query the teacher at z_t</div>
</div>
```

## Assets And Figure Size

**Size each figure by its information density in the rendered PDF**, not by
defaulting to `width: 100%`; use figure-specific print classes or `max-width` /
`max-height`. A single-curve plot, small architecture sketch, or qualitative
example normally takes half a page or less, and near-full-page figures are
reserved for dense multi-panel evidence whose labels would otherwise be
unreadable. **Both directions are layout failures**: an image that is legible
but occupies a whole page, and a dense plot shrunk until its axes or legend
become unreadable — for the latter, crop or split panels, or transcribe key
values into HTML.

- **Prefer figures from the arXiv source package**; rasterize vector PDFs and
  resize very large images before embedding under `assets/<slug>/`. **Rebuild
  LaTeX tables as searchable HTML, never as screenshots.**
- **Keep the browser HTML as the canonical report**; print-only transformations
  belong in a temporary copy.
- **If images are embedded, also render a same-basename PDF**: use the existing
  print override, set a writable `XDG_CACHE_HOME`, pass the tutorials directory
  as WeasyPrint's base URL, and avoid CSS Grid in the print copy. These prevent
  font-cache hangs, missing relative assets, and pathological layout time.

## Inspect The Real PDF Before Delivery

**Browser HTML inspection is not sufficient** — render the actual PDF and look
at every formula/pseudocode page at readable resolution, plus a contact sheet of
the whole document; `pdftotext -layout` is a useful secondary check, never a
replacement for looking. Confirm the intended line count survived, indentation
still carries the right grouping, no token or subscript is clipped, no line
broke at an arbitrary symbol, no block split across pages, each figure's
footprint is proportional to the evidence it carries, and no avoidable blank or
figure-only page appeared.

Exact extraction and rendering snippets from earlier work are kept under
`../archive/legacy/`, for troubleshooting only.
