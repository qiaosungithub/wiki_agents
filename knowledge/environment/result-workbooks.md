# Experiment Result Workbooks

Owns project-to-workbook routing and the current results destinations. Writing
and formatting results is [harness/skills/result-logging/SKILL.md](../../harness/skills/result-logging/SKILL.md).

### Which Tab

**Resolve the project's live tab by title rather than gid, and inspect its header before trusting a saved tab name or row number.**

| Project | Spreadsheet | Tab |
|---|---|---|
| VLM (PaliGemma / JAX LLaVA) | `1FlcygQbGBTqHLJeiKdwxS0nP41SPMJrtX-kCJq8d7SQ` | The cleaned PaliGemma/JAX LLaVA tab |
| Looped nanoGPT (parcae / loopformer / ouro) | `1chHYhhEnTfgkKmLnZiC7jjoFCE-ywsDCxPLXFdSTl20` (its own workbook, `Looped Nanogpt`) | `looped nanogpt (cleaned)` |

New nanoGPT-setting runs default to `looped nanogpt (cleaned)`
([link](https://docs.google.com/spreadsheets/d/1chHYhhEnTfgkKmLnZiC7jjoFCE-ywsDCxPLXFdSTl20/edit#gid=1779859670)),
a pruned copy that keeps the new-weight-recipe blocks and the reference
baselines. Pick the workbook by ID and then the tab by title, because three
older tabs are read-only history and a write into one raises no error: the
unpruned `looped nanogpt` tab in the same workbook, and the `looped nanogpt` and
`Parcae unroll-optim (qiaos)` tabs in the EqR workbook
`17pvrMbOKOKFiIa-eorO8Od12qc5JmrFCSXcXKeoe_u0`. The call/loss-diagonal line's
`nanoGPT (qiaos)` tab is a separate line and stays in the EqR workbook. The
current idea is [knowledge/research/looped_nanogpt_per_site.md](../research/looped_nanogpt_per_site.md).

- The workbooks also hold dated backup tabs, so a stale gid or name can write into a frozen snapshot nobody reads.
- A new line of work opens a titled block at the bottom of the live tab, not a new tab.
