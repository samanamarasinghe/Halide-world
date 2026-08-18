#!/usr/bin/env python3
"""Separate Halide forks that extend the compiler from unmodified re-uploads.

`classify_repos.py` sets aside repositories that embed Halide's own directory
tree under `halide_copy_or_fork`, because paths alone cannot tell an extending
fork from a copy someone re-uploaded. Git history can: fetch each candidate into
a clone of upstream and ask what it has that upstream does not.

Three outcomes, and all three occur in this corpus:

  * shared history, commits ahead   an extending fork. What it changed is the
                                    interesting part -- 29 commits confined to
                                    src/autoschedulers is autoscheduler work,
                                    38 across src/runtime and python_bindings
                                    is a vendor maintaining a production fork.
  * shared history, nothing ahead   an unmodified snapshot. Drop it.
  * no shared history               Halide vendored as a subtree inside a
                                    different project, so judge the project.

Requires a blobless clone of upstream, which is 27MB rather than gigabytes:

    git clone --bare --filter=blob:none https://github.com/halide/Halide.git
    python3 curate/fork_diff.py --repo Halide.git \
        --in data/pools/lane_b_classified.json --out data/pools/fork_verdicts.json
"""

import argparse
import json
import subprocess
import sys


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
    subprocess.run(
        ["git", "-C", repo, "fetch", "--filter=blob:none", "--quiet", remote,
         f"+refs/heads/*:refs/remotes/{remote}/*"],
        capture_output=True, text=True)
    # Take the first ref rather than HEAD: a fetched remote has no HEAD, and
    # `$(rev-parse ... || fallback)` silently concatenates the failure message
    # into the result, which produces a garbage revision and a false "no shared
    # history" for every repository.
    return remote, git(repo, "for-each-ref", "--format=%(objectname)",
                       "--count=1", f"refs/remotes/{remote}/")


def analyse(repo, slug, upstream):
    remote, head = fetch(repo, slug)
    if not head:
        return {"repo": slug, "verdict": "unreachable"}

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
    parser.add_argument("--in", dest="src", default="data/pools/lane_b_classified.json")
    parser.add_argument("--out", default="data/pools/fork_verdicts.json")
    parser.add_argument("--verdict", default="halide_copy_or_fork")
    args = parser.parse_args()
    sys.stdout.reconfigure(line_buffering=True)

    rows = json.load(open(args.src))["repos"]
    candidates = [r["repo"] for r in rows if r.get("verdict") == args.verdict]
    print(f"{len(candidates)} candidates")

    upstream = git(args.repo, "rev-parse", "HEAD", check=True)
    results = []
    for slug in candidates:
        result = analyse(args.repo, slug, upstream)
        results.append(result)
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
