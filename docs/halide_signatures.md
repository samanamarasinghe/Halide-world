# Halide signature set — what is in the grep and why

The path enumeration in `curate/repo_contributors.py` greps a depth-1 checkout
for these tokens. Every candidate was measured across the 8 pilot checkouts
before being admitted, because a generic token quietly poisons the path set and
then the people list built on top of it.

## In

| token | files hit | note |
|---|---|---|
| `using namespace Halide` | 241 | the highest-yield token. Catches Halide code with no include and no `Halide::` prefix |
| `ImageParam` | 96 | Halide-elements 92 |
| `.compute_root(` | 51 | approx-vision 45 |
| `RDom` | 20 | reduction domain, no collisions seen |
| `Halide::` | — | subsumes `Halide::Var`, `Halide::Func`, `Halide::Generator` |
| `Halide.h` | — | covers `#include "Halide.h"` |
| `.compute_at(` | 9 | |
| `halide_`, `HalideBuffer`, `HALIDE_REGISTER`, `find_package(Halide` | — | from the original set |
| `.store_at(` | 3 | |
| `.gpu_tile(` | 1 | |

## Out

| token | why |
|---|---|
| `.tile(` | 26 hits, of which 19 are `torch.tile` in pytorch and 4 are numpy in opencv samples. Almost pure noise |
| `.reorder_storage(` | 0 hits across all 8 repos. Dead weight |

The general lesson matches the one already recorded for the bare word "halide":
a token that is Halide-specific *in Halide's own idiom* is not necessarily
Halide-specific in the wild. `.tile()` is a tensor operation in two of the
largest repos in the index.

## Dedicated vs shared

The token set also decides how a file is judged:

- **DEDICATED** — the filename says halide, **or** the file includes `Halide.h`
  or carries `using namespace Halide`. The file is a Halide translation unit;
  every commit to it counts.
- **SHARED** — anything else that merely mentions Halide. Halide is a minority
  branch inside the project's own code (opencv's layer files under
  `#ifdef HAVE_HALIDE`). Judged with pickaxe `git log -G'[Hh]alide'`.

Keying this on the filename alone was wrong in both directions:

- `fixstars/Halide-elements` had **zero** files whose name says halide, so all
  194 went to pickaxe — which only matches diffs containing the word. A line
  like `output(x,y) = input(x,y)*2;` in a file that is entirely Halide contains
  no such word, so it was undercounted: 388 commits instead of 473.
- `opencv`'s layer files must stay shared, and under the content rule they do.
