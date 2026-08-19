# Artifact edges — the third edge kind, and the gap it exposes

Script: `curate/artifact_edges.py`. Input is `data/pools/artifacts_attributed.json`, which
was attributed but never turned into edges.

| | |
|---|---|
| papers examined | 530 |
| **artifact edges** | **226**, over 190 papers (24 papers ship more than one) |
| distinct repos reached | 213 |
| already Lane B nodes | **15** |
| **reachable only through a paper** | **198** |
| link verdicts in the source | own_artifact 226, mentioned 981, possible_artifact 2 |
| edges whose repo name was truncated in the source text | 2 (kept and flagged) |

Years span 2015-2026. The cues that produced the links are unglamorous and hold up:
"available at" 87, "open-source" 22, "artifact" 20, "is available" 12.

## Why 198 of 213 are new, and why that matters

**Lane B discovered repos by searching GitHub for Halide code signatures.** A repo that
relates to Halide without carrying its code is invisible to that method — which is exactly
the `descendant` role, the fifth value that exists because TVM, Exo and TACO cite Halide
without vendoring it. The project history already records the symptom: *apache/tvm is
absent from Lane B entirely*.

Artifact edges reach those repos by a different route — the paper names its own code:

| reached only via an artifact edge | from |
|---|---|
| `llvm/polygeist` | Retargeting and Respecializing GPU Workloads |
| `pytorch/glow` | Glow: Graph Lowering Compiler Techniques |
| `nicolasvasilache/tensorcomprehensions` | The Next 700 Accelerated Layers |
| `willow-ahrens/finch.jl` | Looplets: A Language for Structured Coiteration |
| `intel/hfav` | High-Performance Code Generation through Fusion and Vectorization |
| `abhijangda/fastkron` | Fast Kronecker Matrix-Matrix Multiplication on GPUs |

So this is not tidying. **It is the only discovery channel the index has for one of its
six roles.**

The 15 that were already nodes are the strongest records in the index — a paper, a repo,
and a link between them, each independently evidenced: `exo-lang/exo`,
`uwplse/rake`, `tiramisu-compiler/tiramisu`, `jingpu/halide-hls`,
`pulp-platform/mempool`, `charguer/optitrust`, `pytorch/pytorch`, `kendryte/nncase`,
`yyuting/adelta`, `tsinghua-ideal/syno`, `sakehl/haliverexperiments`,
`rise-lang/2021-cgo-artifact`, `modern-compilers-lab/gnn_rl_pretrain`,
`mpecenin/wscad-2019`, `halide/halide`.

## What an artifact edge does not say

It asserts that **the paper shipped this code**. It does not assert the repo uses Halide.
~81% of repo references in this literature are incidental, and a paper can cite Halide as
background while its artifact has nothing to do with it. Whether a newly reached repo is
`descendant`, `uses` or `drop` is a curation judgement; the script emits candidates and
says so.

## The decision this raises

Do the 198 enter the repo pool as curatable records needing a role and importance, or stay
artifact-only nodes reachable through their paper?

1. **Admit them to the pool.** Closes the `descendant` blind spot properly, and the site
   can show them beside the code-discovered repos. Cost: 198 more records for the judged
   pass, on top of 262 already queued, and many will land at `drop`.
2. **Keep them as artifact nodes only.** No new curation load; the edge is still visible
   from the paper. Cost: the index continues to under-represent descendants, and a
   researcher looking for "repos related to Halide" will not find Polygeist or Glow.
3. **Admit a scored subset** — those whose paper is itself high-importance, or whose repo
   name or paper title suggests a compiler or DSL. Bounded, but introduces a threshold on
   a population nobody has measured yet.

Option 3 needs the judged pass to have run on the parent papers first, so 1 and 2 are the
live choices today.
