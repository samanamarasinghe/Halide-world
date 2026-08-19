# Contributor edges — the four categories, and the merged person layer

`curate/contributor_edges.py`, 2026-08-19. Reads the 564-repo harvest and the
anchor's own contributor file; writes `data/pools/contributor_edges.json`. Cheap
and re-runnable — it re-clones nothing, so it re-runs whenever the judged pass
refines a repo or the harvest improves.

## Result

**886 people, 1,553 edges, 13 bots excluded and recorded.**

| category | edges | what it means |
|---|---|---|
| `uses` | 1,228 | the default |
| `core` | 221 | halide/Halide itself |
| `packaging` | 63 | distribution trees |
| `extends` | 41 | someone modified Halide |

**24 people carry an `extends` edge** — the population the index exists to
surface, and none of them were visible before this lane. The largest:

| person | repo | commits | share |
|---|---|---|---|
| Jeff Setter | jeffsetter/Halide_CoreIR | 255 | 51% |
| Tzu-Mao Li | jrk/gradient-halide | 247 | 55% |
| Jing Pu | jingpu/Halide-HLS | 244 | 73% |
| Jing Pu | kevinkim06/Halide-FIRRTL | 234 | 62% |
| Jing Pu | jeffsetter/Halide-HLS-f4graph | 215 | 91% |
| Michael Gharbi | jrk/gradient-halide | 78 | 17% |

**232 people appear in more than one repo**, and **87 core contributors also
appear outside the anchor** — 72 as `core`+`uses`, 9 as `core`+`extends`+`uses`.
That overlap is the reason the merge had to be one union-find rather than two
lists joined afterwards.

## Merging: one union-find, not a join

The anchor's 227 people and the harvest's 893 emails are one population observed
twice. Merging them separately and joining afterwards would need a join key, and
any key weaker than the anchor's own rules splits people who use a different
address in someone else's repo. So both populations go through
`contributors.py`'s rules unchanged — email, normalised name, GitHub noreply
handle, email local-part, with placeholders and generic local-parts denied as
keys. **1,120 inputs collapse to 899 nodes.**

Those rules were tuned against this exact history and re-deriving them here would
produce a second, subtly different answer to a solved problem. Their guarantees
carry over intact, which the output shows: `unknown` appears as a name variant on
Andrew Adams, Takuro Iizuka *and* Khouri Giordano, and they remain three people,
because a placeholder is never a merge key.

Spot-check of the widest merges, which is where over-merging would show:

- **Z Stern**, 18 emails, every one a distinct `*.mtv.corp.google.com` host
- **Andrew Adams**, 14 emails across CSAIL, Google roaming hosts and `calculon`
- **Riyadh Baghdadi**, 12, the CSAIL `lanka*` cluster
- **Alex Reinking**, 7 real domains — adobe, berkeley, fb, gmail, google

All are one person under many machines, which is the case these rules exist for.
Over-merging remains worse than under-merging: a split person is visible and
fixable, one person wearing another's commits looks plausible in a chart.

## `share` is recomputed here, never carried

The harvest writes `share` per identity row. A merged person with two emails in
one repo is two rows, so carrying either row's share understates them by exactly
the other's work. It is recomputed against the repo's Halide-touching total.
Checked: no share exceeds 1.0, and no repo's shares sum past 1.0.

## Bots: 13, excluded from nodes, recorded in full

Both rule sets apply. `contributors.py`'s was written against the anchor's
nightly builders, the harvest's against CI accounts in other people's repos, and
neither is a superset of the other — `PyTorch MergeBot` and `R. Ryantm` (the
nixpkgs auto-updater) come only from the harvest rule; `halide-ci[bot]` and
`halide-llvm-updater[bot]` only from the anchor's. One node displays as
`unknown` and is the nightly builder at
`halidenightly@lagrange.ad.corp.google.com`, 1 commit — flagged on the address,
not the name.

Each is kept with the rule that caught it (ruling 11): a silently missing
identity cannot be audited.

## Known gaps

- **Only 16 people carry an `author_id`.** The cross-layer join uses the
  hand-reviewed `person_aliases.json` alone, because the initial-only key is
  never automated. 886 git people against 5,688 authors is a large unjoined
  surface, and it is the next place to spend review effort.
- **The harvest's HEAD-only discovery gap flows through unchanged.** 48 repos,
  56 identity slots, 3.7% of the total, are repos where Halide code was removed
  upstream and the harvest sees only what Lane B sampled. Fixing it is a harvest
  re-run; these edges re-stamp from the new output with no change here.
- **`data/people/halide_contributors.json` is not in the repo** — it needs a
  clone of halide/Halide. This script bootstraps it (blobless bare, ~27MB) rather
  than failing.
