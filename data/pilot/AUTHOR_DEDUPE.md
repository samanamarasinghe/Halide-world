# Author-layer dedupe — measurement and pilot

Sibling of `data/pools/person_aliases.json`, which merges git contributors to authors.
This one merges authors to each other. The two must land together: two of the alias
targets (Alexander J. Root, Jiawen Chen) are themselves split across author ids, so a
contributor joined "to the author record" would otherwise join one of several.

Script: `curate/author_dedupe.py`. It proposes; it applies nothing.

## The space

| | |
|---|---|
| Person records sharing a name with another record | **1,255** across **542 name groups** |
| Groups where every record holds exactly one work | **206** — no coauthor overlap is observable either way |
| Vetoed (see below) | 1 |

## The rule

Two ids of one human never appear on the same author list, but their papers reach the
same collaborators. **Shared coauthors are therefore the evidence**; an identical name on
its own is not, and never was. Records are clustered with union-find, and the record
holding the most works keeps the node.

| Threshold | Clusters | Person records removed |
|---|---|---|
| >=1 shared coauthor | 225 | **275** |
| >=2 | 169 | 203 |
| >=3 | 116 | 137 |

## The veto, and it is not hypothetical

**If two same-named records appear on the SAME paper, no merge happens at any threshold.**
Either they are two different people, or the source listed one author twice; both need a
human. Exactly one case:

> `Zihao Ye` — ids 3060913 and 2402503197 both appear in the author list of *MPK: A
> Compiler and Runtime for Mega-Kernelizing Tensor Programs* (2025).

That group is also **the highest-evidence group in the whole set (19 shared coauthors)**,
so every threshold would have merged it confidently. One case out of 542 does not
threaten the rule, but it does mean the veto has to exist.

## Spot checks

The thin end of >=2 — common names, one work each — reads correct:

| Name | Records | Shared coauthors | Reading |
|---|---|---|---|
| Zhen Zhang | Slapo / Decoupled Model Schedule | Hongzheng Chen, C. Yu | same person |
| Yong Li | IMESH / I-heart-LA | Y. Gingold, Shoaib Kamil | same person |
| Yanjie Wei | conv kernel gen / autoGEMM | Mohamed Wahib, Minwen Deng | same person |
| Yu Liu | **4 records** | Luhong Liang; Ning Li + Zhipeng Wu | **two different Yu Lius**, correctly split into two pairs rather than collapsed into one |

The Yu Liu case is the one worth noting: evidence-driven clustering separated two people of
one name instead of merging them, which a name rule could not do.

Groups whose best evidence is exactly **one** shared coauthor (56 of them, the difference
between the >=1 and >=2 rows). Five sampled, five read correct:

| Name | Shared | Reading |
|---|---|---|
| Chris Fallin | Alexa VanHattum | same person |
| Hugh Leather | Riyadh Baghdadi | same person |
| Tian Zhao | K. Olukotun | same person |
| Huanqi Cao | Shizhi Tang | same person |
| Haibing Guan | Liang Zhu | same person |

**This is a sample, not a precision estimate.** It reads well because the pool is
topically narrow — everything in it cites Halide — so an identical full name plus any
shared collaborator is a stronger signal here than it would be across all of literature.

## What needs deciding

1. **>=1 shared coauthor** — 275 records removed. Recommended: the 56 one-evidence groups
   sampled correct, and the veto covers the failure mode.
2. **>=2** — 203 removed. The conservative cut.
3. **>=3** — 137 removed. Leaves most real duplicates in place.

The 206 one-work groups stay split under all three. No evidence is not counter-evidence:
an unmerged group means "not shown to be the same", not "shown to be different".
