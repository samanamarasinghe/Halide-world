# Contributor harvest — the at-scale runner, 19-repo pilot

`curate/contributor_harvest.py`, 2026-08-19. Stratified pilot: 5 extending forks,
the biggest repos by stars, and a spread of ordinary ones. **Stratified to load
the boundaries, so agreement here is not an accuracy estimate** — the curation
pilot made that mistake once.

## What this lane is

His 2026-08-19 ruling split the contributor lane in two:

- **HARVEST (this file)** — repo -> people + commit counts, **no role stamped**.
  Expensive, checkpointed, re-runnable. Does not wait on curation.
- **EDGE (not yet written)** — stamps `core` / `extends` / `packaging` / `uses`.
  Cheap, re-runs whenever the judged pass refines the `uses` bucket.

The four contribution categories are derivable today: `core` is the anchor,
`extends` is the 8 `fork_diff` extending forks, `packaging` is the 12 trees,
`uses` is everything else. None of them needs the judged pass, which is why the
harvest can run now.

## Pilot results, 19 repos, 161 identities

| repo | mode | people | commits |
|---|---|---|---|
| jeffsetter/Halide_CoreIR | fork_excl | 6 | 493 |
| jrk/gradient-halide | fork_excl | 16 | 451 |
| kevinkim06/Halide-FIRRTL | fork_excl | 8 | 376 |
| jingpu/Halide-HLS | fork_excl | 9 | 336 |
| jeffsetter/Halide-HLS-f4graph | fork_excl | 4 | 236 |
| pytorch/pytorch | path_log | 34 | 175 |
| amansakhuja/buck2 | path_log | 24 | 66 |
| uwplse/rake | path_log | 2 | 60 |
| jeffsetter/Halide-to-Hardware | fork_excl | 3 | 35 |
| opencv/opencv | path_log | 9 | 22 |
| wsmoses/Halide-AS | fork_excl | 2 | 18 |
| MegEngine/MegEngine | path_log | 2 | 10 |
| six more | path_log | 1 each | 2-3 |
| halide/Halide_old_history | fork_excl | 0 | 0 |

`Halide_old_history` at zero is correct: it *is* Halide's pre-rewrite history and
holds nothing of its own.

Cost: 3-15 s per repo, 75 s for the two with deep histories. Disk never held more
than one repo — both clones are deleted the moment the record is written, and the
pilot freed 1.5 GB doing it.

## Three bugs the pilot found, all pre-existing

**1. A fork's extending work need not be on HEAD.**
`jeffsetter/Halide-to-Hardware` reported **zero commits** for a confirmed
extending fork. Its `master` is entirely contained in upstream; every extending
commit sits on `coreir_apps`, `coreir_target`, `hardware_benchmarks` or `hls`.
`fork_authors()` now logs `--branches`, not `HEAD`. **This undercounted every
fork**, not just the visible one: Halide-AS 2 -> 18, Halide-HLS 287 -> 336,
Halide-FIRRTL 329 -> 376, gradient-halide 444 -> 451, Halide-to-Hardware 0 -> 35.

**2. `log_authors` raised `KeyError` on any repo with no dedicated paths.**
An empty path list returned a plain `{}` instead of the `defaultdict`, so the
shared pass crashed on its first author. Invisible until a repo had zero
Halide-named files — `opencv/opencv` and `skourta/benchmark_evaluation` here.
Same class as the other silent-shape bugs in this project: it failed only on the
input nobody had run yet.

**3. The shared-pass budget was modelled on the wrong quantity.**
First guess: history depth x shared-path count, skip above 2,000,000. pytorch
scored 180,000 — comfortably under — and then ran for nine minutes without
finishing. **Pickaxe on a blobless clone fetches one blob per commit that touches
a shared path, so the count of those commits IS the cost.** `rev-list --count
HEAD -- <shared>` returns it without fetching anything. pytorch: 3,134 commits
over 11 paths. halide/Halide: 10,522 over 747.

Budget now 1,500 commits, **provisional** — it fires on exactly those two in the
pilot and on nothing else. It is a stable, explainable omission, unlike a
wall-clock timeout, which moves with the network and which nothing downstream may
key on (the `fork_diff` `fetch_timeout` lesson).

## Open question for him: HEAD-only path discovery misses removed code

`content_paths()` greps a depth-1 checkout, so **a Halide file added and later
deleted is invisible**. The docstring said so; opencv is the first case where it
bites. OpenCV has removed its Halide backend upstream: 7,347 tree files, **one
grep hit, zero Halide-named paths**. The harvest sees 6 layer files from Lane B's
sample and reports 9 people / 22 commits. The 2026-08-18 pilot, which still had
`halide_scheduler.cpp` and `op_halide.cpp` in view, measured 90.

So the lane systematically undercounts **repos that once used Halide and stopped**
— arguably the group whose history matters most, since a dropped dependency is
still a real one. The fix is cheap on a blobless clone: union the paths ever
added, via `git log --diff-filter=A --name-only`, instead of reading HEAD alone.
**Not implemented — his call**, since it changes what the lane counts.

## Also settled here

- **The anchor is out of the default pool.** halide/Halide through this runner
  gives 46 people / 545 commits, because it restricts to Halide-named paths. Its
  227 people come from `curate/contributors.py` over the whole history. Different
  question, and mixing them would silently replace the better answer.
- **Bots are flagged, never dropped** (ruling 11). One in the pilot, in pytorch.
  `is_bot`, `bot_rule` and `bot_matched_on` ride on the person record; the edge
  pass decides what to do with them.
- **Each person carries `share`** — their commits over the repo's Halide-touching
  total, which is his granular ask for how much of a repo someone contributed.
- **The runner bootstraps its own input list.** `lane_b_curatable.json` existed
  only on one disk, because it is built from the gitignored `repo_meta_state.json`
  — the recurring trap in this project. Rather than commit a 395 KB derived blob,
  the runner rebuilds both when they are absent (~6 min against ecosyste.ms),
  the same way `admit_artifact_repos.py` fetches in-script. Verified here from a
  bare clone: anchor 1, curatable 552, drop 102, packaging 12, matching
  2026-08-18 exactly.

## Running the full pool

    python3 -u curate/contributor_harvest.py

552 curatable + 12 packaging, resumable, checkpointed after every repo. At pilot
rates that is a few hours, dominated by clone time, and it re-runs safely.
