# Author-layer dedupe — 2026-08-19

His ruling: resolve the ambiguous groups with a **second signal, no hand
review**. Regenerate with `python3 curate/author_dedupe.py`.

## The asymmetry that makes this tractable

**5,214 author names carry 5,688 S2 ids. 362 names hold more than one id, and
zero ids hold more than one name spelling.** S2 over-splits people and never
conflates them, so the id is a safe atom and the whole problem is "are two
same-name ids one human".

Note this is the *opposite* of the DBLP defect already on record, where two
different Andrew Adamses were merged into one entry. S2 splits, DBLP conflates —
the fix for one is the wrong instinct for the other.

## Signals, measured against a control

The control is random pairs of ids belonging to *different* names — pairs we
know should not merge. A signal is only worth having if it fires far more often
on the target set.

| signal | target | control | verdict |
|---|---|---|---|
| shared coauthor (keyed on **name**) | — | — | primary; links 251 groups |
| 2-hop coauthor | 17% | 4% | kept — real but thin |
| shared venue | 9% | 5% | rejected |
| shared field of study | 98% | 97% | rejected, non-discriminative |

Coauthor overlap must key on coauthor **name**, not coauthor id: an id key is
degraded by the very splitting it is meant to fix, because the coauthor is split
too. Name-keyed links 251 groups where id-keyed links 218.

## Result

| | |
|---|---|
| merged on a shared paper | 1 |
| merged on a shared coauthor | 196 |
| merged via the 2-hop signal | 22 |
| **left split, tagged** | **143** |
| author ids collapsed away | 258 |

**The shared-paper signal was contested and is now ruled.** A parallel session
read two same-named ids in one author list the opposite way — a person appears
once per author list, so co-occurrence should mean two different people or a
source defect, and should VETO the merge rather than force it. His ruling of
2026-08-19: **same paper means same person**; the source duplicated one author
within one list. The one case is `Zihao Ye` (ids 3060913 and 2402503197, both
among the 21 authors of *MPK: A Compiler and Runtime for Mega-Kernelizing Tensor
Programs*, 2025), which is also the group with the most shared coauthors in the
set — so both readings would have acted on it with full confidence, in opposite
directions. Recorded here so the question is not re-opened a third time.

A group merges only when **every** pair inside it is linked. Requiring a clique
is deliberate: linking A–B and B–C does not make A and C the same person, and
merging is transitive — that is how the display name `unknown` once chained four
different halide/Halide contributors into a single node.

The 2-hop signal earned its place on cases like **Andrew Adams**, three ids all
genuinely his (Halide and differentiable programming, 17 works; Burst
photography and median filters, 2; the A𝛿 autodiff and Bonsai papers, 4), and
**Frédo Durand**, two ids.

## What no-hand-review costs, stated plainly

143 groups stay split, and some are obviously one person:

| name | pairs linked | papers per id |
|---|---|---|
| Christophe Dubach | 0/1 | 1, 17 |
| Michel Steuwer | 2/3 | 26, 2, 6 |
| Albert Cohen | 5/6 | 15, 5, 1, 1 |
| Alvin Cheung | 1/3 | 11, 1, 5 |
| Tianqi Chen | 6/10 | 17, 1, 2, 2, 1 |

Dubach is the sharpest case — two ids, no shared coauthor at all, which is
implausible for one compiler researcher and shows the coauthor graph has blind
spots wherever someone's record is thin.

Leaving them split is the deliberate choice, not an oversight: a split person is
visible in the data and fixable later, a falsely merged one is invisible.
**Affiliation strings are the obvious next signal for exactly this residual**,
and they arrive with the affiliations lane.
