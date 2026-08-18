"""Repo cleanup pass — turn the Lane B verdicts into a curatable candidate set.

The pilot found four defects in the Lane B output. This pass fixes all four and
writes its own state file; `lane_b_classified.json` is never rewritten.

1. REDISTRIBUTED FOREIGN SOURCE.  The pilot found 79 candidates whose only
   Halide evidence was a vendored PyTorch install.  The real figure is larger
   and the shape is different: the index is dominated by COPIES of a handful of
   upstream projects that happen to touch Halide.  A directory-prefix rule does
   not catch them, because a copy of PyTorch holds `torch/_inductor/` at its
   natural location with nothing above it.  The rule used here is measured
   instead: a path tail shared by many unrelated repos is a redistributed file,
   its canonical owner is kept, and the copies are dropped.  Keeping the
   canonical matters -- `pytorch/pytorch` and `opencv/opencv` are genuine
   Halide consumers, not noise.

2. THE VENDORED-HALIDE TREE.  `path_kinds` flagged 13 repos, but ~100 have
   every sampled path inside an embedded copy of Halide.  Those repos are mostly
   real (t2sp, heterohalide, lasa all build on Halide) so they are NOT dropped,
   but their `n_matches` counts Halide's own files and must not be read as usage
   intensity.  A flag records that.

3. COPIES THE FORK DETECTOR NEVER SAW.  It ran over 8 candidates picked by
   signature profile.  GitHub's own `fork` flag helps but under-detects badly:
   of 540 enriched repos only 5 carry it, and `wsmoses/Halide-AS` and
   `Zineeddine998/Halide` are plain Halide trees created by download-and-push
   rather than by the fork button.  Whole-tree evidence is the better signal.

4. THE SIX RESOLVED FORK CASES were classified and then left outside the 661.

Roles here follow Saman's rulings of 2026-08-18: `core` is anchors-only,
`extends` requires MODIFYING Halide (merely vendoring or linking it is `uses`),
and `drop` is a real verdict whose records are kept, not deleted.

    python3 curate/cleanup_repos.py \
        --pool data/pools/lane_b_classified.json \
        --meta data/pools/repo_meta_state.json \
        --out data/pools/lane_b_curatable.json
"""
import argparse, json, re, sys, collections

sys.stdout.reconfigure(line_buffering=True)

def path_of(p):
    """Lane B paths are `signature:path`. Return just the path, lowercased."""
    return (p.split(":", 1)[1] if ":" in p else p).lower()


def in_halide_tree(p):
    fp = path_of(p)
    return bool(HALIDE_OWN_DIR.search(fp)) or any(m in fp for m in HALIDE_OWN_MARKERS)


# --- 2. Halide's own directory vocabulary ----------------------------------
# A directory named `halide/` does NOT mean a vendored copy — flashlight has
# its own `pkg/halide/`.  The discriminator is Halide's own file layout.
HALIDE_OWN_DIR = re.compile(r"(^|/)halide[-_]?[0-9._]*/", re.I)
HALIDE_OWN_MARKERS = (
    "test/generator/", "test/integration/", "test/correctness/",
    "tools/gengen", "apps/bgu/", "apps/blur/", "apps/hannk/",
    "apps/wavelet/", "apps/resnet_50/", "apps/lens_blur/",
    "apps/linear_algebra/", "apps/hellobaremetal", "apps/hellandroidcamera2",
    "python_bindings/correctness/", "src/autoschedulers/",
    "share/doc/halide", "cmake/findhalide.cmake",
)

# --- 1. redistributed foreign files ----------------------------------------
# The index is dominated not by Halide users but by COPIES of a handful of
# upstream projects that happen to touch Halide: PyTorch (Inductor has a Halide
# backend), Buck and Buck2 (a `halide_library` build rule), tinygrad, MNN
# (vendors Halide's runtime header) and OpenCV (ships a Halide backend).
# `torch/_inductor/codegen/halide.py` alone appears in 64 distinct repos, of
# which one is pytorch/pytorch.
#
# The rule is measured rather than hand-listed: a path tail shared by many
# unrelated repos is a redistributed file. The canonical owner is kept as a
# real candidate -- PyTorch and OpenCV are genuine Halide consumers -- and the
# copies are dropped. Star count picks the canonical, because a copy of PyTorch
# has near zero stars where PyTorch has tens of thousands.
TAIL_SEGMENTS = 4          # enough to be distinctive without pinning the prefix
MIN_CLUSTER = 5            # distinct repos before a tail counts as redistributed
CANONICAL_STAR_RATIO = 20  # the canonical must outweigh the runner-up this much


def tail(p, k=TAIL_SEGMENTS):
    return "/".join(path_of(p).split("/")[-k:])


def owns_path(repo, t):
    """Does this path's own top segment name the repo? pytorch/pytorch holds
    torch/_inductor/...; a repo bundling MNN holds someone else's demo dir."""
    base = repo.split("/")[-1].lower().replace("-", "").replace("_", "")
    head = t.split("/")[0].lower().replace("-", "").replace("_", "")
    return bool(head) and (head in base or base in head)


def redistributed_clusters(repos, meta):
    """Map each redistributed path tail to (canonical_repo_or_None, members)."""
    share = collections.defaultdict(set)
    for r in repos:
        for p in r["paths"]:
            if in_halide_tree(p):
                continue            # Halide's own tree has its own handling
            t = tail(p)
            if t.count("/") < 2:
                continue            # bare filenames like CMakeLists.txt collide by chance
            share[t].add(r["repo"])

    # Where each repo holds the file, so a nested holder cannot be crowned.
    depth = collections.defaultdict(dict)
    for r in repos:
        for p in r["paths"]:
            t = tail(p)
            fp = path_of(p)
            depth[t][r["repo"]] = min(depth[t].get(r["repo"], 99), fp.count("/"))

    clusters = {}
    for t, members in share.items():
        if len(members) < MIN_CLUSTER:
            continue
        shallowest = min(depth[t].values())
        # Only a repo holding the file at its natural location can be canonical,
        # and only when the path plausibly belongs to it. Without the name test
        # a repo that merely bundles MNN wins the cluster on star count.
        eligible = [r for r in members
                    if depth[t][r] <= shallowest and owns_path(r, t)]
        ranked = sorted(eligible,
                        key=lambda r: (meta.get(r, {}).get("stargazers_count") or 0),
                        reverse=True)
        if not ranked:            # nobody plausibly owns it: every member is a copy
            clusters[t] = (None, members)
            continue
        top = (meta.get(ranked[0], {}).get("stargazers_count") or 0)
        runner = (meta.get(ranked[1], {}).get("stargazers_count") or 0) if len(ranked) > 1 else 0
        # No clear canonical means every member is a copy of something outside
        # our candidate set. Drop them all rather than crown an arbitrary one.
        canonical = ranked[0] if top >= max(CANONICAL_STAR_RATIO * max(runner, 1), 50) else None
        clusters[t] = (canonical, members)
    return clusters


# --- 4. the six fork cases resolved by commit diff, with their rulings ------
RESOLVED_FORKS = {
    "Kowrisaan11/Halide":      ("extends", "29 commits, all in src/autoschedulers"),
    "zivid/zivid-halide-fork": ("extends", "38 commits in runtime and python_bindings"),
    "4vtomat/HalideX":         ("extends", "adds src/CodeGen_MLIR.cpp, a Halide-to-MLIR backend"),
    "akothen/Hydride":         ("extends", "vendored subtree that extends Halide"),
    "RafaeNoor/MISAAL":        ("extends", "vendored subtree that extends Halide"),
    "manya-bansal/gern":       ("uses",    "vendored subtree, a consumer"),
}
CONFIRMED_COPIES = {
    "abadams/Halide":   "unmodified copy",
    "mmoadeli/Halide":  "unmodified copy",
}
ANCHOR_REPOS = {"halide/Halide"}

# A repo whose NAME is Halide-something is a copy or an extending fork.
# wsmoses/Halide-AS and Zineeddine998/Halide both carry the stock Halide README
# and neither carries GitHub's `fork` flag: they were made by download-and-push.
HALIDE_NAMED = re.compile(r"^halide([-_.].*)?$", re.I)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", default="data/pools/lane_b_classified.json")
    ap.add_argument("--meta", default="data/pools/repo_meta_state.json")
    ap.add_argument("--out", default="data/pools/lane_b_curatable.json")
    ap.add_argument("--verdicts", default="uses_source,consumer,generator")
    args = ap.parse_args()

    all_repos = {r["repo"]: r for r in json.load(open(args.pool))["repos"]}
    meta = json.load(open(args.meta))
    wanted = set(args.verdicts.split(","))

    scope = [r for r in all_repos.values() if r["verdict"] in wanted]
    # 4. fold the six resolved fork cases back in.
    for slug in RESOLVED_FORKS:
        if slug in all_repos and all_repos[slug] not in scope:
            scope.append(all_repos[slug])

    clusters = redistributed_clusters(scope, meta)
    print(f"{len(clusters)} redistributed path tails over {len(scope)} repos")

    def foreign(p, repo):
        """Is this path a copy of a redistributed file this repo does not own?"""
        c = clusters.get(tail(p))
        return c is not None and c[0] != repo

    out, counts = [], collections.Counter()
    for r in scope:
        repo, paths = r["repo"], r["paths"]
        m = meta.get(repo, {})
        n = len(paths) or 1
        n_foreign = sum(1 for p in paths if foreign(p, repo))
        n_halide = sum(1 for p in paths if in_halide_tree(p))
        copied_from = sorted({clusters[tail(p)][0] or "an unidentified upstream"
                              for p in paths if foreign(p, repo)})

        rec = {
            "repo": repo,
            "lane_b_verdict": r["verdict"],
            "n_matches": r["n_matches"],
            "n_paths_sampled": len(paths),
            "signatures": r["signatures"],
            # The sample caveat travels with the numbers: Lane B keeps at most
            # six example paths per repo, so these are fractions of a sample.
            "foreign_paths": f"{n_foreign}/{n}",
            "halide_tree_paths": f"{n_halide}/{n}",
            "meta": {k: m.get(k) for k in
                     ("description", "stargazers_count", "language", "fork",
                      "source_name", "topics", "pushed_at")} if "error" not in m
                    else {"unindexed": True},
        }

        # Evidence quality flags. These do not decide role; they tell the
        # curation pass how much the signature evidence is worth.
        flags = []
        if n_halide == n:
            flags.append("evidence_is_halides_own_tree")
        elif n_halide:
            flags.append("evidence_partly_halides_own_tree")
        if not m.get("description") and "error" not in m:
            flags.append("no_description")
        if "error" in m:
            flags.append("not_in_ecosystems_index")

        # Status. `drop` keeps the record; nothing is deleted.
        if repo in ANCHOR_REPOS:
            rec["status"], rec["reason"] = "anchor", "the Halide repo itself"
        elif repo in CONFIRMED_COPIES:
            rec["status"], rec["role"] = "drop", "drop"
            rec["reason"] = CONFIRMED_COPIES[repo]
        elif repo in RESOLVED_FORKS:
            role, why = RESOLVED_FORKS[repo]
            rec["status"], rec["role"] = "curatable", role
            rec["reason"] = f"resolved by commit diff: {why}"
            rec["role_source"] = "fork_diff"
        elif n_foreign == n:
            rec["status"], rec["role"] = "drop", "drop"
            rec["reason"] = ("every sampled path is a redistributed copy of "
                             + ", ".join(copied_from)
                             + "; the repo carries someone else's "
                               "Halide-touching source, not its own")
        elif (n_halide == n
              or (HALIDE_NAMED.match(repo.split("/")[-1])
                  and r["n_matches"] > 100 and n_halide)):
            # A whole tree of Halide's own files: either a copy or an extending
            # fork. Undecidable from signatures -- this is what fork_diff is for.
            rec["status"] = "fork_review"
            rec["reason"] = ("every sampled path is inside a Halide tree; "
                             "needs a commit diff to tell a copy from a fork")
        else:
            rec["status"] = "curatable"

        if m.get("fork") and rec["status"] == "curatable":
            flags.append(f"github_fork_of:{m.get('source_name')}")
        rec["flags"] = flags
        counts[rec["status"]] += 1
        out.append(rec)

    out.sort(key=lambda r: (r["status"], -r["n_matches"]))
    doc = {
        "schema_version": 1,
        "note": ("Cleanup pass over lane_b_classified.json. Dropped records are "
                 "KEPT with status=drop so a later harvest does not rediscover "
                 "and rejudge them. Path fractions are over the <=6 example "
                 "paths Lane B stores, not over every match."),
        "counts": dict(counts),
        "redistributed_clusters": {t: {"canonical": c, "n_repos": len(mem)}
                                   for t, (c, mem) in sorted(clusters.items())},
        "n_repos": len(out),
        "repos": out,
    }
    json.dump(doc, open(args.out, "w"), indent=1)

    # A small companion file. The record file runs to ~400 KB, which is data
    # rather than judgement and is regenerable by re-running this script. What
    # the pass actually DECIDES -- which clusters exist, which repo was crowned
    # canonical, and every dropped repo -- is small enough to keep in the repo.
    summary = {
        "schema_version": 1,
        "note": ("Summary of the cleanup pass. Regenerate everything with "
                 "curate/enrich_repos.py then curate/cleanup_repos.py."),
        "counts": doc["counts"],
        "redistributed_clusters": doc["redistributed_clusters"],
        "fork_review_head": [
            {"repo": r["repo"], "n_matches": r["n_matches"],
             "description": r["meta"].get("description")}
            for r in sorted((x for x in out if x["status"] == "fork_review"),
                            key=lambda y: -y["n_matches"])[:25]],
        "dropped": sorted(r["repo"] for r in out if r["status"] == "drop"),
    }
    sm = args.out.replace(".json", "_summary.json")
    json.dump(summary, open(sm, "w"), indent=1)
    print(f"wrote {args.out} and {sm}")
    for k, v in sorted(counts.items()):
        print(f"  {k:<14} {v}")


if __name__ == "__main__":
    main()
