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

---

# Admission: his ruling is to admit the 198. What that costs, and how each cost is handled

## 1. The head is where the attribution is wrong

The 198 were probed against ecosyste.ms: **177 indexed, 21 not; median 24 stars, 45 with
≥100, 19 with ≥1000.** Reading the 19 high-star claims against their papers shows the
attributor's precision collapses exactly there:

| claim | paper | verdict |
|---|---|---|
| `meta-llama/llama3` | Tempo: Compiled Dynamic Deep Learning | **wrong** — a workload, not the artifact |
| `llvm/llvm-project` | PolyGym | **wrong** — the substrate |
| `nvidia/apex` | FlashAttention | **wrong** — the artifact is Dao-AILab/flash-attention |
| `onnx/models` | Explore as a Storm… | **wrong** — a benchmark source |
| `nvidia/cutlass` | Stream-K | **wrong as a node** — upstreamed into it, not its artifact |
| `google-research/google-research` ×2 | two unrelated papers | **wrong as a node** — a monorepo |
| `seannaren/deepspeech.pytorch` | TensorFlow-vs-PyTorch study | **wrong** — matched on the word "pytorch" in the title |
| `pytorch/benchmark` | PyTorch 2 | **weak** — real but not the paper's artifact |
| `mit-han-lab/bevfusion` | TorchSparse++ | **near miss** — right lab, wrong repo (torchsparse) |
| `mitsuba-renderer/mitsuba3` | Dr.Jit | **near miss** — right group, wrong repo (drjit) |
| `pytorch/glow`, `mirage-project/mirage`, `tensor-compiler/taco`, `mit-han-lab/torchsparse`, `beehive-lab/tornadovm`, `ubiquitouslearning/mllm`, `maratyszcza/nnpack`, `bytedance-seed/triton-distributed` | their own papers | **correct** |

The mechanism is legible: the cue is a phrase like "open-source" or "available at" near a
URL, and the attributor pairs it with the nearest link — which may be a workload, a
dependency or a baseline. **Precision is worst on famous repos precisely because papers
mention famous repos.**

**Handling: hand-review the 19 heads before admission.** That is the whole exposure and it
is bounded; the review above is most of it. Below 1000 stars the population is small
research repos where "available at <url>" is nearly always the artifact.

## 2. An automatic gate was tried and does not work

Token overlap between repo name/owner and paper title rejects 7 of the 8 known-bad claims —
but also rejects `uwplse/rake`, `llvm/polygeist`, `willow-ahrens/finch.jl`, `yyuting/adelta`
and `mirage-project/mirage`, all correct. **115 of 226 edges match on neither name nor
owner.** Artifact names routinely have nothing to do with paper titles, so the gate costs
more real edges than it saves false ones. Recorded so it is not rebuilt; hand-review of the
head is cheaper and does not misfire.

## 3. The 21 that ecosyste.ms does not index

Re-probed against `raw.githubusercontent`: **10 have a reachable README and are real** (the
known "404 means not indexed, not gone" finding). **11 have no README on master or main**
and stay unverified — `adcastel/cgo`, `baco-authors/baco-artifact.git`,
`ceruleangu/block-sparse`, `fpsg-uiuc/teaal`, `hips/autogradr`,
`intellabs/parallelaccelerator.jl`, `kenny67nju/lambdagent.1`, `openabl/790`,
`qiyingwu/scanweaver`, `snu-codelab/atim.git`, `souffle-ae/souffle.git`. Two of them
(`ceruleangu/block-sparse`, `fpsg-uiuc/teaal`) come from the truncated source links, and
several show the tell of a bad parse — a trailing `.git`, a bare number, `autogradr` for
`autograd`. **Handling: admit with `unverified_name`, never silently.**

## 4. The schema consequence, and it is the dangerous one

Every Lane B record carries `signatures`, `paths` and `n_matches`. **These 198 carry none,
because they were never found by code search.** Any rule, tier score or site facet that
reads those fields sees zero and can conclude "no Halide evidence" — dropping exactly the
repos this lane exists to surface. The project has hit this shape before: *a zero-hit
result is a reason to look harder, never to drop*.

**Handling: every admitted record carries `discovered_via: artifact_edge`, and anything
keyed on signature counts must branch on it.** Their evidence is the parent paper, so the
judged pass should read the paper, not the repo.

## 5. Curation load

+198 records on top of the 262 already queued, and many will land at `drop`. Unavoidable
under this ruling — but the parent paper gives each one evidence the Lane B tail often
lacks, so they are not evidence-poor in the way the 502 papers are.
