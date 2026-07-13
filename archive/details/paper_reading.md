# Paper Reading — Deep-Reading Report Spec

How to read a paper for the user and produce a **deep-reading HTML report**. This
is the canonical checklist; every paper-reading report must follow it.

- **Reports live in:** `/kmh-nfs-ssd-us-mount/code/qiao/work/readings/vision-related/tutorials/`
- **One card per report** registered in that folder's `index.html`.
- **Style template:** copy the `<style>` block + page skeleton from
  `tutorials/openvision3_deep_reading.html` verbatim (CSS vars, `.hero/.kicker/.pill/.nav`,
  two-column `main` + sticky `.toc`, `.card`, `.grid/.box`, `.note/.warn/.green`,
  `.formula`, `.metric` tables, inline-SVG `.diagram/.caption`). Do not restyle.
- **Language:** body in 简体中文; keep technical terms / identifiers in English.
- **Filename:** `<slug>_deep_reading.html` (e.g. `repae_deep_reading.html`).

## Required sections (in this order)

1. **基础信息** — a `.metric` table with: full **Title**, complete **Authors**
   (keep equal-contribution / corresponding markers), **Team/Affiliations**,
   **Time** (arXiv version + date, and venue if any), arXiv id, local PDF link,
   project/code link. Put a one-line plain-language subtitle in the `.hero`.
2. **Story 概括** — open the report (a "先给结论" card) with the paper's *story*:
   what problem, what key insight, what it claims. Lead paragraph + a 2×2 `.grid`
   of 它想解决什么 / 核心方案 / 最重要结果 / 和我最相关.
3. **任务定义** — for any topic the user may not know, write the task definition
   explicitly: inputs → outputs, the setup, and the evaluation metrics. Don't
   assume familiarity.
4. **方法 + recipe + ablation 细节** — method overview first (an SVG `.diagram`
   helps), then concrete recipe, then **all ablations** as native HTML `.metric`
   tables. Where it helps, **insert real figures/tables parsed from the arXiv
   source tar** (see pipeline). Embedded figures go in `assets/<slug>/*.png`,
   referenced with `<img>` inside a `.diagram` div + a `.caption`.
   - **If the report embeds images**, also render the report to **PDF** (same
     basename) with WeasyPrint so the user can download a single portable file.
5. **深远影响 + 锐评** — discuss the work's broader impact and likely **follow-up
   directions** (for famous papers, name the actual follow-ups); then an
   insider's **limitations 锐评**.
6. **对我的启发** — keep this established section: how it connects to the user's
   own research (AR optical-flow + diffusion render, confidence-routed gen,
   image/video gen). This is a standing preference, not optional.

## Pipeline (reproducible)

Environment has **no poppler** (`pdftoppm`/`pdfinfo` absent). Available:
`pypdf`, `fitz` (PyMuPDF), `PIL`, `weasyprint`, `pandoc`, `reportlab`; network OK.

**WeasyPrint gotchas (learned the hard way — all three will silently waste many minutes):**
1. **`XDG_CACHE_HOME` MUST be set to a writable dir** (e.g. `export XDG_CACHE_HOME=/tmp/fccache`).
   If unset, WeasyPrint hangs at 0% CPU in fontconfig forever (looks like a freeze; import
   itself is fast ~1s). With it set, a text-only page renders in ~1s.
2. **CSS Grid is pathologically slow.** `.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr))}`
   with substantial box content blows up WeasyPrint's track-sizing (one grid card → 8+ min;
   small-content grids slip by). Fixed as part of the print stylesheet below (grid→flex).
2b. **The template is wide-screen 2-column (content + 286px sticky TOC) — it renders UGLY in print**
   (content squeezed to half-page, CJK wraps every few chars, fonts look huge). For the PDF render,
   inject a **print stylesheet** that hides the TOC, makes `main` single-column full-width, shrinks
   fonts, sets A4 margins, and swaps grid→flex. Append it after `</style>` in a temp copy (keep the
   original HTML untouched for browsers). A reusable copy lives at
   `tutorials/_pdf_print_override.html`; its essential rules:
   `@page{size:A4;margin:12mm} body{font-size:13px;background:#fff} main{display:block;max-width:none;padding:0}
   .toc{display:none} .hero{padding:20px} h1{font-size:28px} h2{font-size:20px} .lead/.subtitle~14px
   .card{padding:15px} .grid{display:flex;flex-wrap:wrap;gap:12px} .grid>.box{flex:1 1 calc(50% - 6px)}
   .metric{font-size:11px} img{max-width:100%}` — all with `!important` where overriding.
   Result: ~31 print-pages → ~13, full-width and readable. (Grid boxes may stack full-width in print;
   that's fine and reads well.)
3. **Pass `--base-url <tutorials_dir>/`** when rendering a temp copy that lives elsewhere (e.g. /tmp),
   or relative `assets/...` images resolve to the wrong dir and embed nothing (tell-tale: tiny PDF).
4. **Downscale images by PIXEL width (≤~1800), not just file size** — a 6904px-wide PNG can be small
   on disk yet make WeasyPrint crawl. Single images render fast in isolation; the killer is grid, not images.

Working invocation:
```bash
export XDG_CACHE_HOME=/tmp/fccache
# write grid->flex temp copy of report.html to /tmp/report.flex.html, then:
weasyprint --base-url /…/tutorials/ /tmp/report.flex.html /…/tutorials/report.pdf
```

```python
# 1. text + first-page metadata
from pypdf import PdfReader
r = PdfReader(path)                      # len(r.pages) for page count
for i,p in enumerate(r.pages): open(f'/tmp/<k>_{i:02d}.txt','w').write(p.extract_text() or '')

# 2. find arXiv id (export API; quote-less 'all:' query is most robust)
#    http://export.arxiv.org/api/query?search_query=all:<keywords>&max_results=5

# 3. download source tar, list figure files
#    curl -sL -A Mozilla/5.0 https://arxiv.org/e-print/<id> -o k.tar ; tar -xf k.tar -C k/

# 4. render figure PDFs -> PNG (vector figures), copy raster ones
import fitz
pix = fitz.open(figpdf)[0].get_pixmap(matrix=fitz.Matrix(2,2)); pix.save(out)

# 5. shrink large PNGs (max width ~1800, optimize) with PIL  -> keep <~2MB each

# 6. HTML -> PDF (only when images embedded)
#    weasyprint report.html report.pdf
```

Notes / gotchas:
- arXiv figure files are usually **vector PDF** (need fitz rasterize); some are
  png/jpg (copy directly). Tables are LaTeX, not images — reproduce them as
  native HTML `.metric` tables (searchable, lighter) rather than scraping.
- Embed `<img>` as `<div class="diagram"><img style="width:100%;height:auto;
  border-radius:8px;border:1px solid var(--line)"><div class="caption">…</div></div>`
  — works without touching the shared CSS.
- WeasyPrint renders the report cleanly but sticky TOC / some grid render
  differently in print; that's fine for a download artifact.
- Independent reports parallelize well across subagents (one paper each); give
  each subagent the template path, its `/tmp/<k>_*.txt` text, its
  `assets/<slug>/` image list, and this spec.
