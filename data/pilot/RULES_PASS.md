# Rules pass — the tail, judged by rule

Run 2026-08-19 under his rulings: **paper cut 4, repo cut 3, citation weighting
unchanged, Buck / tinygrad / MNN added back by hand, `packaging` its own role
value.** Regenerate with `python3 curate/rules_pass.py`.

Design rule: a rule fires **only when confident**; everything else escalates.
`escalate = head OR evidence=poor OR no rule fired`.

## Coverage

| | records | decided by rule | escalated | head | evidence poor | no rule fired |
|---|---|---|---|---|---|---|
| papers | 1,941 | 783 (40%) | 1,158 | 261 | 502 | 395 |
| repos | 568 | 313 (55%) | 255 | 41 | 56 | 158 |

Repos are 568 rather than 552 because the 12 packaging trees and the 4 manual
canonicals are decided outright and carried in the same file.

**The paper escalation is dominated by a data gap, not by weak rules.** 502 of
the 1,158 have no citation context and no abstract — there is nothing for any
rule to read. That is the same 463 zero-context S2 records plus the OpenCitations
records without abstracts. No rule refinement touches them; only full text does.

## What fired

| rule | role | n |
|---|---|---|
| S2 marks the Halide citation as methodological | uses/2 | 347 |
| cites Halide as background only | writes-about/1 | 352 |
| citing sentence lists Halide among examples | writes-about/1 | 80 |
| citing sentence states the work uses Halide | uses/2 | 4 |
| incidental Halide reference, no Halide claim in its own words | uses/1 | 269 |
| description or README states it builds on Halide | uses/2 | 28 |
| distribution package tree | packaging/1 | 12 |
| commit diff against upstream already ruled | extends or uses | 4 |
| canonical added by hand | uses/2 | 4 |

## The citing sentence was being thrown away

The compact pool keeps only an intent label and a count; `lane_a.json` keeps the
actual citing sentences. The rules were reading the compact pool, so 384 of the
479 unreachable papers had their best evidence sitting unread on disk. Reading it
moved coverage from 36% to 40%.

The lift is smaller than the finding deserves because the context regexes are
deliberately narrow — `CTX_USES` fired only 4 times. A sentence like "we
implement our pipeline in Halide" is easy; most citing sentences describe the
cited work rather than the citing one. This is where a judged pass earns its
keep, and the sentences are now available to feed it.

## Never decided by rule

- a paper with Halide in its title
- a paper marked influential on an anchor (`is_key`)
- a repo whose name is `Halide` or `Halide-*` — copy vs fork is what the commit
  diff is for
- anything whose text claims to extend, modify, patch or fork Halide.
  `extends` is the most expensive role to get wrong and is never assigned by
  regex

## Two precision misses in the sample, both in the repo rules

1. `Copy of Tyler's Distributed Halide work, but with mods for tiramisu
   comparison` was ruled `uses`. The description says *copy* and *mods* — this
   is a `drop` or an `extends`, not a `uses`. The extends-phrase regex does not
   catch "mods".
2. `Fetches the root directories of the top github repositories to generate
   training data` was ruled `uses/1` by the residual rule. It is not a Halide
   user in any sense; it matched a signature incidentally.

Both come from the same place, and it is the largest firing group.

## The one ruling this pass needs

The residual rule assigns **`uses` at importance 1 to 269 repos** — low stakes,
a handful of signature matches, and nothing about Halide in the project's own
words. Given the measured finding that ~81% of repo references in this corpus
are incidental, the alternatives are:

1. keep `uses/1` — it did link Halide, and importance 1 already says "barely"
2. `drop` — an incidental reference is not a relationship worth a node
3. split on whether Halide appears anywhere in the project's own words at all

Option 3 is measurable and is what I would test next.
