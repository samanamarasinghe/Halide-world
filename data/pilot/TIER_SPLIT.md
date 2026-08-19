# Tier split — the measurement, no cut set

Run 2026-08-19. **No cut is chosen here.** Per the standing rule, the space is
measured first and the cut is yours. Regenerate with
`python3 curate/tier_split.py`.

## What is being scored

**Stakes, not evidence strength.** Splitting on evidence would send all the
evidence-poor records to the tail, which is exactly where rules cannot judge
them. Stakes asks a different question: how much does it cost to get *this*
record's role wrong?

So two axes come out, not one:

- `tier` — head or tail, by stakes
- `evidence` — ok / thin / poor, whether a rule could answer at all

and the judged pass must see **head OR evidence=poor**.

Stakes is deliberately not importance. FlashAttention has 5,034 citations and
importance 1 within the Halide world; citations mean "many people will look at
this record", which is stakes. Anchor breadth and the influential flag are the
Halide-specific counterweights.

## Papers — 1,941 records

```
  score | count
      0 |   657  ############################################################
      1 |   522  ###############################################
      2 |   308  ############################
      3 |   193  #################
      4 |   120  ##########
      5 |    70  ######
      6 |    32  ##
      7 |    21  #
      8 |    11  #
      9 |     2
     10 |     3
     11 |     1
     13 |     1
```

evidence: **ok 671, thin 753, poor 517**

| cut | head | tail | poor in tail | judged pass |
|---|---|---|---|---|
| 2 | 762 | 1179 | 421 | 1183 |
| 3 | 454 | 1487 | 483 | 937 |
| **4** | **261** | **1680** | **502** | **763** |
| 5 | 141 | 1800 | 512 | 653 |
| 6 | 71 | 1870 | 516 | 587 |
| 7 | 39 | 1902 | 517 | 556 |
| 8 | 18 | 1923 | 517 | 535 |

The judged-pass column barely moves above cut 5 — it is floored at ~517 by the
evidence-poor records, which escalate regardless of tier. Raising the cut past
5 therefore buys almost nothing: it shrinks the head without shrinking the work.

## Repos — 552 records

```
  score | count
      0 |   321  ############################################################
      1 |   139  #########################
      2 |    51  #########
      3 |    26  ####
      4 |     7
      5 |     6
      6 |     1
      7 |     1
```

evidence: **ok 265, thin 224, poor 63**

| cut | head | tail | poor in tail | judged pass |
|---|---|---|---|---|
| 2 | 92 | 460 | 55 | 147 |
| **3** | **41** | **511** | **56** | **97** |
| 4 | 15 | 537 | 63 | 78 |
| 5 | 8 | 544 | 63 | 71 |

The repo side is far cheaper than the paper side — READMEs closed most of the
evidence gap (549 of 661 repos have one), so only 63 repos are evidence-poor.

## Top of each list, as a sanity check

Papers by stakes: AKG 13.0, Model-Based Warp Overlapped Tiling 11.0, Hidet 10.5,
Ansor 10.0, Breaking the computation and communication abstraction barrier 10.0,
TVM 9.0, the sparse iteration space transformation framework 9.0, PolyMage 8.0,
DNNVM 8.0, TenSet 8.0, Allo 8.0.

Repos by stakes: jingpu/Halide-HLS 7.0, jeffsetter/Halide_CoreIR 6.0,
Tiramisu 5.0, wsmoses/Halide-AS 5.0, kevinkim06/Halide-FIRRTL 5.0,
jrk/gradient-halide 5.0, OAID/AutoKernel 5.0, StanfordAHA/Halide-to-Hardware
4.0, fixstars/Halide-elements 4.0, approx-vision 4.0, hdr-plus 4.0, opencv 4.0.

The repo head is dominated by the extending forks, which is what the scoring
intends — those are the most expensive records to misfile.

## Calibration question worth your eye

AKG (90 citations) scores above TVM (2,117 citations) because the influential
flag and anchor breadth outweigh the citation band. That is stakes behaving as
designed, but if you would rather the judged pass see the famous records first,
the citation weight should go up.

## Two defects the run exposed, both fixed

1. The duplicate filter keyed on fields that do not exist in `duplicates.json`,
   so nothing was filtered and TVM appeared twice. Groups are lists whose FIRST
   id is the winner — the winner is pinned by position, so group order must
   never be re-sorted downstream.
2. The OpenCitations-only papers are not in `lane_a_compact.json` and were
   silently absent, losing MLIR and the Gharbi/Durand demosaicking paper. They
   are folded in from the enrichment state, keyed `oc:<doi>`.

## Open discrepancy

This rebuild yields **1,941 curatable papers where the record says 1,955**. The
same note already records a 1,955-vs-1,953 wobble from an earlier rebuild, so
the duplicate winners need pinning explicitly rather than by list position.
Not papered over here.
