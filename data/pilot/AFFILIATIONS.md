# Affiliations — where they were when that happened

Run 2026-08-19. Affiliation is a property of the **authorship edge**, not of the
person: someone at Stanford in 2013 and at MIT in 2019 has two true answers and
the index must carry both.

Regenerate with `curate/resolve_dois.py` then `curate/harvest_affiliations.py`.

## Getting a key at all

`lane_a.json` carries no DOI — only title, venue, year, authors. Crossref is
keyed on DOI, so the lane could not start. The map that used to supply them
lived in a gitignored state file on one disk; it is now rebuilt from scratch by
`curate/resolve_dois.py`: **1,482 of 1,840 works carry a DOI**, 357 genuinely
have none, 0 errors, 18 minutes.

That run exposed a live defect worth carrying forward. **The keyless Semantic
Scholar frontend endpoint still works but has changed shape** — the payload is
now wrapped in a `PAPER_DETAIL` envelope with the paper one level down, where it
used to sit at the top level. Reading the DOI field from the top level yields
nothing for every paper, which is indistinguishable from *this paper has no
DOI*. The parser accepts both shapes and reports the resolved count, which is
the number that would expose the next change.

## Coverage is publisher-shaped, and that is structural

1,631 papers, 7,449 authorship slots, **5,283 carrying a raw affiliation (70%)**.

| registrant | slots with an affiliation |
|---|---|
| ACM | 3,688 / 3,699 |
| IEEE | 1,160 / 2,139 |
| Wiley | 79 / 79 |
| Springer | 0 / 576 |
| Elsevier | 0 / 278 |
| Nature | 0 / 57 |

Springer and Elsevier deposit no affiliations in Crossref at all. This is not a
gap to retry — retrying Elsevier forever is the shape of a loop that never
finishes — so those papers are recorded as `no_affiliation_deposited` with their
registrant. The 177 hard errors are all http 404, and **147 of them are arXiv
DOIs, which Crossref does not hold**. Also structural.

The corpus is favourably distributed: ACM 658 and IEEE 358 are 68% of the 1,482
resolved DOIs, and ACM is where this literature publishes.

## What it settled in the person layer

Affiliation is the strongest signal measured for the author dedupe, against the
same control of random different-name id pairs:

| signal | target | control |
|---|---|---|
| **affiliation** | **67%** | **2%** |
| 2-hop coauthor | 17% | 4% |
| shared venue | 9% | 5% |
| shared field | 98% | 97% |

Folded into `author_dedupe.py`, it takes the residual from **143 groups down to
117** and collapses 297 author ids rather than 258. It settled **Christophe
Dubach** — two ids, 1 and 17 papers, no shared coauthor at all — which was the
sharpest example of what no-hand-review was costing.

**The remaining 117 are mostly a coverage problem, not a signal one**: 92 of
them have at least one pair where one id carries no affiliation, because of the
Springer, Elsevier and arXiv gap above. Each residual record now carries
`affiliation_known` per id so the two causes stay distinguishable.

## Still to do in this lane

The raw strings are harvested but not yet normalised to institutions. The rules
for that already exist in `curate/affiliations.py`: the printed string is ground
truth, OpenAlex may only corroborate it, and the acronym-expansion rule was
tried and rejected because it turned ARM into the American Rock Mechanics
Association and MIT into the Moscow Institute of Thermal Technology.
