# Evidence

Verbatim findings from work whose checkout no longer exists. Kept for the
measurements and the reject branches actually exercised — never to decide how
the system works today. Every rule these back already lives in a core guide.

| File | Backs |
|---|---|
| `20260803_bigstore_probe.md` | A Borg job can read an external GCS bucket through `/bigstore` with the prod identity — the GO that unblocked the migration |
| `20260803_cc12m_copy.md` | First proof of the same-region guard; measured bigstore->CNS throughput |
| `20260803_cc12m_cns_copy.md` | CNS-to-CNS is the fast leg as well as the free one |
| `20260803_cc12m_to_god.md` | Moving a payload onto group quota, with every reject branch exercised |

Pre-restructure copies of the core guides used to sit here too. They were
byte-identical to what git already holds, so they were deleted; recover one with
`git show b3ef8dd:<xmanager|data_locality|spreadsheet|filesystem_latency>.md`.
