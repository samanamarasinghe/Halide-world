#!/usr/bin/env python3
"""Separate Halide forks that extend the compiler from unmodified re-uploads.

`classify_repos.py` sets aside repositories that embed Halide's own directory
tree under `halide_copy_or_fork`, because paths alone cannot tell an extending
fork from a copy someone re-uploaded. Git history can: fetch each candidate into
a clone of upstream and ask what it has that upstream does not.

Four outcomes, and all four occur in this corpus:

  * shared history, commits ahead   an extending fork. What it changed is the
                                    interesting part -- 574 commits confined to
                                    apps/autoscheduler is autoscheduler work,
                                    35 across apps/hardware_benchmarks and
                                    src/CodeGen_CoreIR_Target.cpp is a hardware
                                    backend.
  * shared history, nothing ahead   an unmodified snapshot. Drop it.
  * no shared history               Halide vendored as a subtree inside a
                                    different project, so judge the project.
                                    A repo NAMED Halide landing here is a
                                    download-and-push copy, not a subtree; the
                                    diff cannot tell those apart.
  * did not fetch in time           usually a large distribution tree that
                                    merely packages Halide. Re-verified alive
                                    rather than reported as missing.

Requires a blobless clone of upstream, which is 27MB rather than gigabytes:

    git clone --bare --filter=blob:none https://github.com/halide/Halide.git
    python3 curate/fork_diff.py --repo Halide.git \
        --in data/pools/lane_b_curatable.json --status fork_review \
        --out data/pools/fork_verdicts.json
"""

import argparse
import json
import os
import subprocess
import sys


FETCH_TIMEOUT = 45    # seconds; a Halide fork fetches in a few, a huge unrelated project does not


def git(repo, *args, check=False):
    result = subprocess.run(["git", "-C", repo, *args],
                            capture_output=True, text=True)
    if check and result.returncode:
        raise RuntimeError(result.stderr.strip())
    return result.stdout.strip()


def fetch(repo, slug):
    """Add the candidate as a remote and fetch its branches without blobs."""
    remote = slug.replace("/", "_")
    git(repo, "remote", "remove", remote)
    git(repo, "remote", "add", remote, f"https://github.com/{slug}.git")
    try:
        subprocess.run(
            ["git", "-C", repo, "fetch", "--filter=blob:none", "--quiet", remote,
             f"+refs/heads/*:refs/remotes/{remote}/*"],
            capture_output=True, text=True, timeout=FETCH_TIMEOUT)
    except subprocess.TimeoutExpired:
        # Some candidates are large unrelated projects that merely vendor
        # Halide. Time out rather than let one stall a 110-repo run.
        return remote, ""
    # Take the first ref rather than HEAD: a fetched remote has no HEAD, and
    # `$(rev-parse ... || fallback)` silently concatenates the failure message
    # into the result, which produces a garbage revision and a false "no shared
    # history" for every repository.
    return remote, git(repo, "for-each-ref", "--format=%(objectname)",
                       "--count=1", f"refs/remotes/{remote}/")


def prune(repo, slug):
    remote = slug.replace("/", "_")
    for ref in git(repo, "for-each-ref", "--format=%(refname)",
                   f"refs/remotes/{remote}/").splitlines():
        git(repo, "update-ref", "-d", ref)
    git(repo, "remote", "remove", remote)


def analyse(repo, slug, upstream):
    remote, head = fetch(repo, slug)
    if not head:
        # Distinguish gone from merely enormous. In this corpus all nine were
        # alive -- six FreeBSD ports trees, a nixpkgs tree and two research
        # monorepos -- so reporting them as "unreachable" hid a real category.
        try:
            subprocess.run(["git", "ls-remote", "--heads",
                            f"https://github.com/{slug}.git"],
                           capture_output=True, timeout=30, check=True)
            return {"repo": slug, "verdict": "fetch_timeout",
                    "note": "repository exists but did not fetch within "
                            f"{FETCH_TIMEOUT}s; usually a large distribution "
                            "tree that merely packages Halide"}
        except Exception:
            return {"repo": slug, "verdict": "gone_or_private"}

    base = git(repo, "merge-base", upstream, head)
    if not base:
        return {"repo": slug, "verdict": "vendored_subtree",
                "note": "no shared history with upstream; Halide is embedded in "
                        "a different project, so judge that project"}

    ahead = int(git(repo, "rev-list", "--count", f"{base}..{head}") or 0)
    behind = int(git(repo, "rev-list", "--count", f"{base}..{upstream}") or 0)
    diverged = git(repo, "log", "-1", "--format=%ad", "--date=short", base)

    touched = {}
    if ahead:
        names = git(repo, "log", "--name-only", "--format=", f"{base}..{head}")
        for line in names.splitlines():
            if not line.strip():
                continue
            parts = line.split("/")
            key = "/".join(parts[:2]) if len(parts) > 1 else parts[0]
            touched[key] = touched.get(key, 0) + 1

    return {
        "repo": slug,
        "verdict": "extending_fork" if ahead else "unmodified_copy",
        # Halide's history was rewritten at some point -- halide/Halide_old_history
        # is an official repo. A fork predating the rewrite shares only an ancient
        # merge-base, so `commits_ahead` reads in the tens of thousands where the
        # real divergence is small. Trust `touched`, not the count.
        "ahead_inflated_by_history_rewrite": ahead > 5000,
        "commits_ahead": ahead,
        "commits_behind": behind,
        "diverged": diverged,
        "touched": dict(sorted(touched.items(), key=lambda kv: -kv[1])[:6]),
        "subjects": git(repo, "log", "--format=%s", f"{base}..{head}").splitlines()[:5]
        if ahead else [],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default="Halide.git")
    parser.add_argument("--in", dest="src", default="data/pools/lane_b_curatable.json")
    parser.add_argument("--out", default="data/pools/fork_verdicts.json")
    parser.add_argument("--verdict", default="halide_copy_or_fork",
                        help="select on the raw lane_b `verdict` field")
    parser.add_argument("--status", default=None,
                        help="select on the cleanup pass's `status` field instead, "
                             "e.g. fork_review")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    sys.stdout.reconfigure(line_buffering=True)

    rows = json.load(open(args.src))["repos"]
    if args.status:
        candidates = [r["repo"] for r in rows if r.get("status") == args.status]
    else:
        candidates = [r["repo"] for r in rows if r.get("verdict") == args.verdict]
    if args.limit:
        candidates = candidates[:args.limit]

    # Resume: fetching 110 repositories is slow enough that an interrupted run
    # must not start over.
    results, done = [], set()
    if os.path.exists(args.out):
        results = json.load(open(args.out))["repos"]
        done = {r["repo"] for r in results}
    candidates = [c for c in candidates if c not in done]
    print(f"{len(candidates)} to analyse, {len(done)} already done")

    upstream = git(args.repo, "rev-parse", "HEAD", check=True)
    for i, slug in enumerate(candidates, 1):
        result = analyse(args.repo, slug, upstream)
        results.append(result)
        # Flush every repository, not every tenth: a fetch is slow enough that
        # losing nine of them to an interrupted run is real work.
        json.dump({"schema_version": 1, "repos": results},
                  open(args.out, "w"), indent=1)
        # Drop the candidate's refs so its objects become unreachable. Many
        # candidates are large unrelated projects that merely vendor Halide;
        # keeping their histories grew the object store past 4 GB.
        prune(args.repo, slug)
        if i % 20 == 0:
            subprocess.run(["git", "-C", args.repo, "gc", "--prune=now", "--quiet"],
                           capture_output=True, timeout=600)
        if result["verdict"] == "extending_fork":
            where = ", ".join(f"{k} ({v})" for k, v in result["touched"].items())
            print(f"  {slug:28s} EXTENDS  +{result['commits_ahead']} commits  {where}")
        elif result["verdict"] == "unmodified_copy":
            print(f"  {slug:28s} copy     {result['commits_behind']} behind, "
                  f"diverged {result['diverged']}")
        else:
            print(f"  {slug:28s} {result['verdict']}")

    with open(args.out, "w") as handle:
        json.dump({"schema_version": 1, "repos": results}, handle, indent=1)
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
