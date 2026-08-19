#!/usr/bin/env python3
"""Materialize the paper -> repo ARTIFACT edges, and report what they reach.

The graph model has three edge kinds: authorship, contribution and artifact. The first
two are built. This is the third, and it was sitting in `data/pools/artifacts_attributed.json`
already attributed but never turned into edges.

WHAT THE EDGES EXPOSE, and it is a structural gap rather than a tidying job:

    Lane B discovered repos by searching GitHub for HALIDE CODE SIGNATURES. A repo that
    cites Halide without carrying its code is therefore invisible to it -- which is the
    whole `descendant` category, the fifth role value that exists because TVM, Exo and
    TACO relate to Halide without vendoring it. The history already records that
    apache/tvm is absent from Lane B entirely.

    Artifact edges reach those repos by a different route: the paper names its own code.
    Of 213 distinct repos named as a paper's own artifact, only 15 are already Lane B
    nodes. The other 198 -- llvm/polygeist, pytorch/glow, tensorcomprehensions,
    willow-ahrens/finch.jl -- are reachable no other way.

So this is not a dedupe or a cleanup. It is the only discovery channel the index has for
one of its six roles.

WHAT THE EDGE DOES NOT ASSERT: that the repo uses Halide. An artifact edge is a fact
about the PAPER (this is the code that paper shipped), and ~81% of repo references in this
literature are incidental. Whether a newly reached repo is `descendant`, `uses` or `drop`
is a curation judgement, not something this script decides. It emits candidates and says
so.

    python3 curate/artifact_edges.py --out data/pools/artifact_edges.json
"""
import argparse
import collections
import json


def load(path):
    with open(path) as f:
        return json.load(f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--attributed", default="data/pools/artifacts_attributed.json")
    ap.add_argument("--repos", default="data/pools/lane_b.json")
    ap.add_argument("--out")
    args = ap.parse_args()

    papers = load(args.attributed)["papers"]
    pool = {(r.get("repo") or "").lower() for r in load(args.repos)["repos"]}

    edges, verdicts = [], collections.Counter()
    for p in papers:
        for link in p.get("links") or []:
            v = link.get("verdict")
            verdicts[v] += 1
            if v != "own_artifact":
                continue
            repo = link["repo"]
            edges.append({
                "paper": p["s2_id"],
                "title": p.get("title"),
                "year": p.get("year"),
                "repo": repo,
                "in_repo_pool": repo.lower() in pool,
                "reasons": link.get("reasons"),
                # A truncated link was cut off in the source text, so the repo name may be
                # partial. Kept and flagged rather than dropped: a wrong name is visible,
                # a silently missing edge is not.
                "truncated": link.get("truncated", False),
            })

    repos = {e["repo"].lower() for e in edges}
    known = {e["repo"].lower() for e in edges if e["in_repo_pool"]}
    new = sorted(repos - known)
    trunc = [e for e in edges if e["truncated"]]

    print(f"papers examined: {len(papers)}")
    print(f"link verdicts: {dict(verdicts)}")
    print(f"artifact edges: {len(edges)} over {len({e['paper'] for e in edges})} papers")
    print(f"distinct repos reached: {len(repos)}")
    print(f"  already Lane B nodes: {len(known)}")
    print(f"  NOT in the repo pool -- reachable only through a paper: {len(new)}")
    print(f"edges whose repo name was truncated in the source text: {len(trunc)}")

    if args.out:
        with open(args.out, "w") as f:
            json.dump({
                "schema_version": 1,
                "note": "An artifact edge asserts the paper shipped this code. It does "
                        "NOT assert the repo uses Halide; that is a curation judgement.",
                "n_edges": len(edges),
                "n_repos": len(repos),
                "n_repos_new": len(new),
                "edges": edges,
                "repos_not_in_pool": new,
            }, f, indent=1)
        print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
