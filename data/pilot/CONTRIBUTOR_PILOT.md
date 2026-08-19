# Contributor pilot — people whose commits touch Halide code

Run 2026-08-18. **Status: unintegrated.** These names are repo-scoped. They are
not merged across repos and are not linked to the person layer.

## The question

Repos beyond the anchor have empty people lists. Crediting a repo's *main*
contributors is wrong when Halide is a small part of it. The rule instead: credit
only people whose commits actually touch Halide code.

## Why not the GitHub API

GitHub commit search indexes the commit **message** only — there is no path or
diff qualifier, and the code-search REST endpoint is still legacy syntax without
`path:`. Searching commits for "Halide" finds people who wrote the word.
Actions is compute, not a search primitive.

`git log -- <paths>` on a `--filter=blob:none` clone has no rate limit and
answers the question directly. Shipped as `curate/repo_contributors.py`.

## The 8 repos, 2 per axis

| repo | axis | Lane B matches | paths found | commits attributed |
|---|---|---|---|---|
| pytorch/pytorch | big | 4 | 16 | 129 (dedicated only) |
| opencv/opencv | big | 15 | 28 | 90 |
| mbuckler/ReversiblePipeline | small | 1 | 9 | 33 |
| cucapra/approx-vision | small | 130 | 134 | 42 |
| fixstars/Halide-elements | lots of Halide | 257 | 194 | 388 |
| jrk/gradient-halide | lots of Halide (fork) | 441 | — | 444 |
| flashlight/flashlight | little Halide | 7 | 6 | 9 |
| pulp-platform/mempool | little Halide | 8 | 13 | 8 |

## Names

- **ReversiblePipeline** — Mark Buckler 33 (sole contributor)
- **mempool** — Samuel Riedel 7, Matheus Cavalcante 1 (both ETH Zurich)
- **flashlight** — Jacob Kahn 5 across two emails, Ryan Guo 2, three one-offs
- **approx-vision** — Mark Buckler 37, Taehoon Lee 5
- **Halide-elements** — Takashi Osawa 98, Momoko Kono 77, Izumi Asakura 72,
  Takuro Iizuka 53, Akira Maruoka 28, +8 more. Entirely a Fixstars team
- **gradient-halide** — Tzu-Mao Li 247, Michael Gharbi 77, then Johnson 37 and
  Adams 27. The differentiable-Halide authors. Ragan-Kelley does not top his own
  fork
- **opencv** — Dmitry Kurtaev 25 (wrote the Halide backend), Alexander Alekhin 32
  across two emails, 24 people in all
- **pytorch** — `PyTorch MergeBot` 44 is the top entry, then Jason Ansel 37
  (Inductor lead, and the OpenTuner author)

## Four findings, each a bug the pilot caught

**1. Path enumeration must be a content grep, not filename matching.**
`fixstars/Halide-elements` is Halide code end to end and not one filename says
"halide". Filename-only: 6 paths, 20 commits. Grep: 194 paths, 388 commits.

**2. Dedicated files and shared files need different treatment.**
`modules/dnn/src/layers/convolution_layer.cpp` is OpenCV's own code with a Halide
branch inside it, so a plain path-log counts every unrelated commit — opencv came
out at 824. Judging shared files with pickaxe `git log -G'[Hh]alide'` gives 90,
and Kurtaev rises to the top where he belongs.

**3. A fork needs double exclusion, and this is the history rewrite again.**

| exclusion | result |
|---|---|
| none | Adams 11,454 / Johnson 4,586 / Sharlet 4,102 |
| `--not halide/Halide` | Adams 5,659 — still wrong |
| `--not` Halide **and** Halide_old_history | 444 commits: Li 247, Gharbi 77 |

Halide's history was rewritten, so a fork's base commits are unreachable from
current upstream and read as the fork's own work.

**4. Pickaxe on a blobless clone of a huge repo is pathological.** It fetches
blobs one at a time over the network. pytorch's 11 shared files ran past 25
minutes and were killed; its 5 dedicated files returned instantly. Big repos need
a full clone, or dedicated files only.

## Open, not yet ruled on

- Bots. `PyTorch MergeBot` outranks the actual author
- Identity is email-keyed, so Alekhin, Kurtaev and Kahn each split in two.
  Under-merging is the safe direction but inflates people counts
- No threshold. One drive-by lint commit to a Halide file currently earns a place
- Paths are enumerated at HEAD, so a Halide file added and later deleted is
  invisible
