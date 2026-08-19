#!/usr/bin/env python3
"""Turn the artifact-edge repos into repo-pool records, per his 2026-08-19 ruling.

`curate/artifact_edges.py` finds 213 repos named as a paper's own artifact, of which 198
were never discovered by Lane B's GitHub code search -- the `descendant` blind spot, since
a repo that relates to Halide without carrying its code cannot be found by searching for
Halide code. This script prepares those 198 for admission.

THREE THINGS IT DOES, EACH ANSWERING A MEASURED FAILURE:

    discovered_via     Every Lane B record carries `signatures`, `paths` and `n_matches`.
                       These carry NONE, because code search never found them. A rule,
                       tier score or site facet keyed on those fields reads zero and
                       concludes "no Halide evidence" -- dropping exactly the repos this
                       lane exists to surface. Every record is stamped
                       `discovered_via: artifact_edge`; anything reading signature counts
                       must branch on it. THE EVIDENCE IS THE PARENT PAPER.

    head_review        The attributor pairs a cue ("open-source", "available at") with the
                       nearest link, so precision collapses on famous repos -- because
                       papers mention famous repos. All 19 candidates with >=1000 stars
                       were read against their paper by hand; 10 are rejected and the
                       reason is recorded per repo rather than deleted.

    unverified_name    11 repos are not indexed by ecosyste.ms AND serve no README on
                       master or main. Several show the tell of a bad parse: a trailing
                       `.git`, a bare number, `hips/autogradr` for autograd. Two come from
                       source links that were truncated mid-URL. They are admitted with
                       the flag, never silently.

An automatic gate was tried and REJECTED: token overlap between repo name/owner and paper
title rejects 7 of 8 known-bad claims but also rejects rake, polygeist, finch.jl, adelta
and mirage, all correct. 115 of 226 edges match on neither. Artifact names routinely have
nothing to do with paper titles, so the gate costs more real edges than it saves false
ones. Hand-reviewing 19 heads is cheaper and does not misfire.

    python3 curate/artifact_edges.py --out data/pools/artifact_edges.json
    python3 curate/admit_artifact_repos.py --out data/pools/artifact_repos.json
"""
import argparse
import json

# Read against each claim's own paper, 2026-08-19. Only repos with >=1000 stars needed
# this: below that the population is small research repos where the cue is nearly always
# the artifact.
HEAD_REVIEW = {
    "meta-llama/llama3": ("reject", "a workload Tempo evaluates on, not its artifact"),
    "llvm/llvm-project": ("reject", "the substrate PolyGym builds on, not its artifact"),
    "nvidia/apex": ("reject", "FlashAttention's artifact is Dao-AILab/flash-attention"),
    "onnx/models": ("reject", "a benchmark model zoo, not the paper's artifact"),
    "nvidia/cutlass": ("reject", "Stream-K was upstreamed into it; not the paper's own repo"),
    "google-research/google-research": ("reject", "a monorepo claimed by two unrelated papers"),
    "seannaren/deepspeech.pytorch": ("reject", "matched on the word pytorch in the paper title"),
    "pytorch/benchmark": ("reject", "real repo, but not the PyTorch 2 paper's artifact"),
    "mit-han-lab/bevfusion": ("reject", "right lab, wrong repo - TorchSparse++ ships mit-han-lab/torchsparse"),
    "mitsuba-renderer/mitsuba3": ("reject", "right group, wrong repo - Dr.Jit ships mitsuba-renderer/drjit"),
    "pytorch/glow": ("keep", "Glow's own repo"),
    "mirage-project/mirage": ("keep", "the paper's own repo"),
    "tensor-compiler/taco": ("keep", "the paper's own repo"),
    "mit-han-lab/torchsparse": ("keep", "the paper's own repo"),
    "beehive-lab/tornadovm": ("keep", "the paper's own repo"),
    "ubiquitouslearning/mllm": ("keep", "the paper's own repo"),
    "maratyszcza/nnpack": ("keep", "the paper's own repo"),
    "bytedance-seed/triton-distributed": ("keep", "the paper's own repo"),
}

# ecosyste.ms 404 AND no README on master or main. An ecosyste.ms 404 alone means only
# "not indexed" -- 10 other misses served a README and are real.
UNVERIFIED_NAME = {
    "adcastel/cgo", "baco-authors/baco-artifact.git", "ceruleangu/block-sparse",
    "fpsg-uiuc/teaal", "hips/autogradr", "intellabs/parallelaccelerator.jl",
    "kenny67nju/lambdagent.1", "openabl/790", "qiyingwu/scanweaver",
    "snu-codelab/atim.git", "souffle-ae/souffle.git",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--edges", default="data/pools/artifact_edges.json")
    ap.add_argument("--meta", help="optional ecosyste.ms probe output, repo -> metadata")
    ap.add_argument("--out")
    args = ap.parse_args()

    with open(args.edges) as f:
        edges = json.load(f)["edges"]
    meta = {}
    if args.meta:
        with open(args.meta) as f:
            meta = json.load(f)

    by_repo = {}
    for e in edges:
        if e.get("in_repo_pool"):
            continue
        by_repo.setdefault(e["repo"].lower(), []).append(e)

    records = []
    for repo, es in sorted(by_repo.items()):
        m = meta.get(repo) or {}
        ok = m.get("ok")
        rec = {
            "repo": repo,
            "discovered_via": "artifact_edge",
            "papers": [{"s2_id": e["paper"], "title": e.get("title"),
                        "year": e.get("year"),
                        "cue": (e.get("reasons") or [None])[0]} for e in es],
            "stars": m.get("stars") if ok else None,
            "description": (m.get("desc") or None) if ok else None,
            "language": m.get("lang") if ok else None,
            "archived": m.get("archived") if ok else None,
            "fork": m.get("fork") if ok else None,
        }
        if repo in UNVERIFIED_NAME:
            rec["unverified_name"] = True
        if any(e.get("truncated") for e in es):
            rec["truncated_source_link"] = True
        if repo in HEAD_REVIEW:
            rec["head_review"], rec["head_review_reason"] = HEAD_REVIEW[repo]
        records.append(rec)

    rejected = [r for r in records if r.get("head_review") == "reject"]
    print(f"candidates {len(records)}  rejected at head {len(rejected)}  "
          f"admitted {len(records) - len(rejected)}")
    print(f"  unverified_name {sum(1 for r in records if r.get('unverified_name'))}"
          f"  truncated source link {sum(1 for r in records if r.get('truncated_source_link'))}")

    if args.out:
        with open(args.out, "w") as f:
            json.dump({
                "schema_version": 1,
                "note": "Repos reached ONLY through a paper's artifact edge. "
                        "discovered_via=artifact_edge means the record carries no "
                        "signature/path/n_matches evidence, because code search never "
                        "found it -- anything keyed on those fields must branch on this "
                        "flag. The evidence is the parent paper. A head_review of "
                        "'reject' is kept with its reason rather than deleted, so the "
                        "judgement can be audited.",
                "n_candidates": len(records),
                "n_rejected_at_head": len(rejected),
                "n_admitted": len(records) - len(rejected),
                "repos": records,
            }, f, indent=1)
        print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
