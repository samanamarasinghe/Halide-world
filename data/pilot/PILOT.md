# Curation pilot — 20 papers, 20 repos

A stratified sample judged against the role facet and an importance score, put
up for critique before the rubric is run over 1,955 papers and 661 repos.

The sample is **not random**. It was chosen to load the boundaries of the
rubric — every role value, the known-hard cases, and a deliberate group of
records with no textual evidence at all. Agreement on this set is therefore not
an estimate of accuracy on the full set; it is a test of whether the rules
decide the hard cases the way you want them decided.

---

## The rubric as applied

**Role** is a property of the record's *relationship to Halide*, not of the
work itself. It is single-valued, resolved by precedence when more than one
value fits:

    core  >  extends  >  descendant  >  uses  >  writes-about

| Value | Test |
|---|---|
| `core` | Is Halide, or a component that lands in the Halide codebase, by the Halide team |
| `extends` | Adds capability to Halide — backend, frontend, autoscheduler, verification — and the result carries or links Halide code |
| `descendant` | Inherits Halide's design ideas (algorithm/schedule separation, a scheduling language) and carries no Halide code |
| `uses` | Runs Halide, or Halide-generated code, as a tool for something else |
| `writes-about` | Cites, surveys or compares Halide without running or inheriting it |

The discriminator between `extends` and `descendant` is **whether the artifact
carries Halide code**. That rule is what separates Halide-HLS from Exo.

**Importance** is significance *within the Halide world* on 1–4. It is
deliberately not general impact, and the pilot contains cases where the two
diverge by three orders of magnitude in citation count.

| | |
|---|---|
| 4 | Landmark — the Halide world cannot be described without it |
| 3 | Significant — a substantial contribution to or through Halide |
| 2 | Relevant — a real Halide connection, of interest inside a subarea |
| 1 | Peripheral — passing citation; Halide is incidental |

A sixth verdict, **`drop`**, was needed and is not in the current facet. Four of
the twenty repos are not Halide artifacts at all.

---

## Papers

Evidence is the citing sentence Semantic Scholar returns, plus which anchor was
cited. Confidence is mine, not a computed score.

| # | Paper | Venue / yr | Cits | Role | Imp | Conf | Basis |
|---|---|---|---|---|---|---|---|
| 1 | Verified lifting of stencil computations | PLDI'16 | 98 | `extends` | 3 | high | "STNG translates them into a high-performance stencil DSL called Halide" — a Fortran frontend onto Halide |
| 2 | TVM | OSDI'18 | 2117 | `descendant` | 4 | high | "builds on Halide's idea of decoupling"; carries no Halide code today |
| 3 | Tiramisu | CGO'19 | 316 | `descendant` | 3 | high | Scheduling-language lineage; compares against distributed Halide |
| 4 | Exocompilation (Exo) | PLDI'22 | 67 | `descendant` | 3 | high | "In sharp contrast to Halide, Exo adopts…" — Ragan-Kelley authorship does not make it `core` |
| 5 | Taichi | TOG'19 | 189 | `descendant` | 3 | high | "We use interval analysis for bounds inference as in Halide" — inherits a technique, no code |
| 6 | A sparse iteration space transformation framework (TACO) | OOPSLA'20 | 73 | `descendant` | 3 | high | Scheduling language and autoscheduler both modelled on Halide's |
| 7 | Fireiron | PACT'20 | 38 | `descendant` | 2 | high | "Fireiron is inspired by Halide… but no existing framework treats data movements as first-class" |
| 8 | Composable and Modular Code Generation in MLIR | arXiv'22 | 42 | `descendant` | 3 | **med** | Substantive positioning against Halide; boundary case with `writes-about` — see Q3 |
| 9 | Burst photography for HDR and low-light imaging (HDR+) | TOG'16 | 566 | `uses` | 4 | high | "Most of our code is written in Halide"; "we have implemented our own FFT in Halide". Halide's flagship deployment; Adams and Sharlet authorship does not make it `core` |
| 10 | Sample-based Monte Carlo denoising | TOG'19 | 105 | `uses` | 3 | high | "We implement our kernel-splatting operation in Halide". Artifact: `adobe/sbmc` |
| 11 | Synthetic depth-of-field on a single-camera phone | TOG'18 | 202 | `uses` | 3 | high | "Our code was implemented in Halide, then manually scheduled for the CPU" |
| 12 | Performance evaluation of Halide auto-scheduler with DCC interpolation | SPIE'23 | 1 | `uses` | 2 | high | Squarely a Halide evaluation; small reach |
| 13 | FPGA HLS Today | TRETS'22 | 177 | `writes-about` | 3 | high | Surveys Halide-HLS, HeteroHalide, GENESIS, T2S-Tensor. Best single map of the Halide-on-FPGA subtree, hence 3 |
| 14 | Vectorization for DSPs via equality saturation (Diospyros) | ASPLOS'21 | 72 | `writes-about` | 2 | **low** | Contexts are comparative only. Flagged Tier-2 at anchor time; the evidence does not support `extends`. Wants the PDF |
| 15 | The Deep Learning Compiler: A Comprehensive Survey | TPDS'21 | 253 | `writes-about` | 1 | high | Halide appears once, in a list of backend toolchains |
| 16 | Domain-specific hardware accelerators | CACM'20 | 235 | `writes-about` | 1 | high | Halide named as an example DSL needing a backend |
| 17 | FlashAttention | NeurIPS'22 | 5034 | `writes-about` | 1 | high | Halide cited as an instance of a class of compilers; not used. **5,034 citations, importance 1** |
| 18 | Automatic Generation of Efficient Accelerators for Reconfigurable Hardware | ISCA'16 | 107 | `writes-about` | 2 | **low** | **No contexts.** Stanford Spatial/Delite line, not the Halide-to-Hardware paper the title suggests. Wants the PDF |
| 19 | Alive2 | PLDI'21 | 155 | `writes-about` | 1 | med | **No contexts**, but it cites only the Halide term-rewriting anchor, which places it as related work on verified rewriting |
| 20 | ML to Solve Vehicle Routing Problems: A Survey | T-ITS'24 | 109 | `writes-about` | 1 | **low** | **No contexts**, no plausible Halide connection. Suspected false citation edge |

Distribution: `core` 0, `extends` 1, `descendant` 7, `uses` 4, `writes-about` 8.

`core` came out empty because the anchor set was excluded from the curatable
pool by construction — see Q1.

---

## Repos

Judged from the signature profile plus GitHub metadata and README, both fetched
keylessly (see `curate/enrich_repos.py`).

| # | Repo | ★ | Role | Imp | Conf | Basis |
|---|---|---|---|---|---|---|
| 1 | halide/halide.github.com | 5 | `core` | 3 | high | The project's own website |
| 2 | jingpu/Halide-HLS | 74 | `extends` | 4 | high | "HLS branch of Halide" — Pu et al. |
| 3 | StanfordAHA/Halide-to-Hardware_archive | 82 | `extends` | 4 | high | Halide-to-Hardware, the AHA line |
| 4 | UCLA-VAST/heterohalide | 15 | `extends` | 3 | high | "From Image Processing DSL to Efficient FPGA Acceleration" |
| 5 | haoxiaochen/t2sp | 1 | `extends` | 3 | med | T2SP, spatial architectures. **`fork: true`** — canonical repo is elsewhere; wants redirecting |
| 6 | pku-liang/lasa | 0 | `extends` | 2 | high | "Productive and Performant Linear Algebra on FPGAs", vendors Halide |
| 7 | 4vtomat/HalideX | 5 | `extends` | 2 | high | "Halide with multi-dimensional load/store IRs" — a Halide-to-MLIR backend. **Not currently in the 661** — see Q5 |
| 8 | wsmoses/Halide-AS | 1 | *unresolved* | 2 | **low** | Stock Halide README, 566 matches all inside Halide's own tree. Copy or autoscheduler work, undecidable without a commit diff |
| 9 | Tiramisu-Compiler/tiramisu | 960 | `descendant` | 3 | med | Its Halide code is `benchmarks/halide/*_ref.cpp` — baselines, not backbone. Paper is `descendant`; the repo carries Halide code, which by rule would say `extends`. See Q2 |
| 10 | fixstars/Halide-elements | 87 | `uses` | 3 | med | "Elemental code snippets written in Halide language" — a library *in* Halide, adding no Halide capability. See Q4 |
| 11 | adobe/sbmc | 92 | `uses` | 3 | high | Artifact of paper 10 |
| 12 | cucapra/approx-vision | 67 | `uses` | 3 | high | Artifact of "Reconfiguring the Imaging Pipeline", a paper only OpenCitations found |
| 13 | ISI-apex/halide-sar-app | 4 | `uses` | 2 | high | "A SAR application written in Halide" |
| 14 | chamikasudusinghe/halide-data | 0 | `uses` | 2 | med | No README; 1,318 matches over tutorial and `random_pipeline` samples — machine-generated schedule data |
| 15 | scanner-research/scanner | 624 | `uses` | 2 | high | 4 matches, all under `examples/how-tos/halide/`. Optional integration in a popular repo — the mirror of FlashAttention |
| 16 | EricHuGuangyu/FluidSimulation | 0 | `uses` | 1 | **low** | Every match is inside `jni/Halide/share/doc/` — a bundled Halide distribution's own documentation. May not use Halide at all |
| 17 | Zineeddine998/Halide | 0 | **`drop`** | — | high | Unmodified old Halide copy, stock README. Same class as abadams/Halide |
| 18 | rrbpalm/hunter-gate | 1 | **`drop`** | — | high | The Hunter CMake package manager; one match in a packaging example |
| 19 | Ottowski/warhammer-ai-chatbot | 0 | **`drop`** | — | high | A Warhammer rules chatbot. Matches only via a bundled PyTorch install |
| 20 | neptun-software/github.repository.fetcher | 0 | **`drop`** | — | high | Scrapes repos into training data; the match is inside scraped JSON |

Distribution: `core` 1, `extends` 6, `descendant` 1, `uses` 7, `drop` 4,
unresolved 1.

---

## Four measurements the pilot forced

**1. 32% of the paper pool has no textual evidence.** Of 1,955 curatable
papers, 463 have zero citation contexts and 157 are OpenCitations-only records
carrying a DOI and nothing else — no title, venue, author or abstract. On the
620 together, role can only be guessed from metadata. Pilot paper 18 is the
demonstration: its title reads as a Halide-to-Hardware paper and it is not one.
The 157 need enrichment before they can be curated at all.

**2. 79 of the 661 repo candidates are PyTorch false positives.** Their only
Halide evidence is `torch/_inductor/codegen/halide.py` inside a bundled PyTorch
install. This is the OpenCV finding a second time, with a twist:
`pytorch/pytorch` itself is in the candidate set and correctly so — Inductor has
a real Halide backend. The fix is not to drop the signal but to drop it when the
path sits inside a bundled dependency directory (`_internal/`, `site-packages/`,
`venv/`, `node_modules/`).

**3. The vendored-Halide detector under-fires by an order of magnitude.** 102
candidates have every sampled path inside an embedded Halide tree and 46 more
have some; `path_kinds` flagged 13. For those repos `n_matches` counts Halide's
own files, so it is not a usage-intensity signal and must not be used as one.
Caveat: `paths` is capped at six per repo, so this is measured on a sample, not
the full match list.

**4. The fork detector was scoped too narrowly.** It ran over 8 candidates
chosen by signature profile. `wsmoses/Halide-AS` and `Zineeddine998/Halide` are
both plain Halide trees that it never saw, and `haoxiaochen/t2sp` carries
GitHub's own `fork: true` flag. The metadata enrichment names forks outright and
should gate the commit-diff pass rather than a signature heuristic.

---

## Open questions

1. **Is `core` anchors-only by construction?** The 15 anchors are excluded from
   the curatable pool, and no non-anchor paper in the pilot earns `core`. Either
   `core` is a label the anchors carry and the pool never uses, or the anchors
   should be folded back in as curated records with `role: core`.

2. **Is role a property of the record or of the system?** Tiramisu's paper is a
   `descendant` and Tiramisu's repo links Halide. Same for TVM if its early
   HalideIR history is counted. Per-record is more honest and lets the site show
   the split; per-system is tidier to read.

3. **Where does MLIR structured codegen sit?** It positions against Halide at
   length without inheriting the schedule/algorithm split. `descendant` or
   `writes-about` — this decides a sizeable MLIR cluster, not one paper.

4. **Is a library written in Halide `uses` or `extends`?** `fixstars/Halide-elements`
   adds no capability to Halide but is reusable Halide infrastructure. The answer
   also covers the Halide `apps/` ecosystem.

5. **The six resolved fork cases are outside the 661.** Three extending forks and
   three vendored subtrees (Hydride, MISAAL, manya-bansal/gern) were classified
   but never merged back into the candidate set. They should be, giving 667.

6. **`drop` as a sixth verdict.** Four of twenty repos are not Halide artifacts.
   Without it they have to be forced into `writes-about`, which would be false.

Minor: reconstructing the curatable set from the committed files gives 1,955,
not the 1,953 recorded. Two duplicate groups resolve to a different winner than
the original run. Worth pinning the winner explicitly in `duplicates.json`.
