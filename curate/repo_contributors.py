#!/usr/bin/env python3
"""Find people whose commits touch Halide code inside a non-anchor repo.

The non-anchor repos have no people list, and crediting a repo's MAIN
contributors is wrong when Halide is a small part of it. This attributes only
commits that actually touch Halide.

Why git and not the GitHub API: commit search indexes the commit MESSAGE only --
there is no path or diff qualifier -- and the code-search REST endpoint is still
legacy syntax without path:. `git log -- <paths>` on a blobless clone has no
rate limit and is the only primitive that answers the question.

Path set = tree paths matching /halide/i + a CONTENT GREP of a depth-1 checkout
+ the sampled paths Lane B recorded. The grep is not optional: fixstars/Halide-
elements is Halide code end to end and not one filename says "halide"
(filename-only found 6 paths / 20 commits; grep found 194 / 388).

Paths are then split two ways:
  dedicated -- the file is Halide's; every commit to it counts
  shared    -- Halide is a branch inside the project's own code, so a plain
               path-log counts unrelated commits (opencv came out at 824).
               Judged with pickaxe `git log -G'[Hh]alide'` instead -> 90.

FORKS need separate handling, see fork_authors() at the bottom.
"""
import json, os, re, subprocess, sys, time
from collections import defaultdict

WORK = os.environ.get("HALIDE_CLONES", "/tmp/clones")
HALIDE_RE = re.compile(r"halide", re.I)

# Halide's own directory vocabulary -> an embedded Halide tree, not the repo's work
VENDORED_MARKERS = [
    "src/CodeGen_", "tools/GenGen.cpp", "test/correctness/", "test/integration/",
    "apps/bgu/", "apps/blur/", "apps/hannk/", "python_bindings/", "src/runtime/",
]
BUNDLED_DIRS = ("_internal/", "site-packages/", "venv/", "node_modules/", "third_party/", "3rdparty/")

GREP_RE = r'Halide\.h|Halide::|HalideBuffer|halide_|find_package\(Halide|Halide::Generator|HALIDE_REGISTER'


def sh(args, cwd=None, timeout=600):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)


def clone(repo):
    """Bare blobless clone: carries every commit and tree, fetches no blobs.
    Enough for path-limited `git log`. NOT enough for pickaxe -- see run()."""
    d = os.path.join(WORK, repo.replace("/", "__"))
    if os.path.exists(os.path.join(d, "HEAD")) or os.path.isdir(os.path.join(d, ".git")):
        return d
    os.makedirs(WORK, exist_ok=True)
    t = time.time()
    r = sh(["git", "clone", "--bare", "--filter=blob:none",
            f"https://github.com/{repo}.git", d], timeout=1800)
    if r.returncode != 0:
        return None
    print(f"    cloned in {time.time()-t:.0f}s", flush=True)
    return d


def tree_paths(d):
    r = sh(["git", "ls-tree", "-r", "HEAD", "--name-only"], cwd=d)
    return [p for p in r.stdout.splitlines() if p]


def content_paths(repo):
    """Depth-1 checkout of HEAD, grepped. Catches files whose name says nothing.
    NOTE: HEAD only -- a Halide file added and later deleted is invisible."""
    d = os.path.join(WORK, "shallow__" + repo.replace("/", "__"))
    if not os.path.isdir(d):
        t = time.time()
        r = sh(["git", "clone", "--depth=1", "--quiet",
                f"https://github.com/{repo}.git", d], timeout=1800)
        if r.returncode != 0:
            print(f"    shallow clone FAILED: {r.stderr[:150]}")
            return []
        print(f"    shallow checkout in {time.time()-t:.0f}s", flush=True)
    r = sh(["grep", "-rIlE", GREP_RE, "."], cwd=d, timeout=900)
    return [p[2:] for p in r.stdout.splitlines() if p.startswith("./") and "/.git/" not in p]


def pick_paths(all_paths, sampled, grepped=()):
    hits = set(p for p in all_paths if HALIDE_RE.search(p))
    hits |= set(grepped)
    for p in sampled:
        p = p.split(":", 1)[1] if ":" in p else p
        hits.add(p)
    kept, vendored, bundled = [], [], []
    for p in sorted(hits):
        if any(b in p for b in BUNDLED_DIRS):
            bundled.append(p)
        elif any(m in p for m in VENDORED_MARKERS):
            vendored.append(p)
        else:
            kept.append(p)
    return kept, vendored, bundled


def log_authors(d, paths, bulk_limit=200, rev_args=None, pickaxe=False, people=None):
    """pickaxe=True keeps only commits whose diff adds or removes a Halide line."""
    if not paths:
        return (people if people is not None else {}), 0, 0
    fmt = "%x01%H%x02%an%x02%ae%x02%aI%x02%s"
    args = ["git", "log", f"--format={fmt}", "--name-only"]
    if pickaxe:
        args += ["-G", "[Hh]alide"]
    args += list(rev_args or [])
    args += ["--"] + paths
    r = sh(args, cwd=d, timeout=3600)
    if people is None:
        people = defaultdict(lambda: {"commits": 0, "files": 0, "names": set(),
                                      "first": None, "last": None, "examples": []})
    bulk = total = 0
    for rec in r.stdout.split("\x01"):
        if not rec.strip():
            continue
        head, _, body = rec.partition("\n")
        parts = head.split("\x02")
        if len(parts) < 5:
            continue
        _sha, an, ae, aI, subj = parts[0], parts[1], parts[2], parts[3], parts[4]
        files = [f for f in body.splitlines() if f.strip()]
        total += 1
        if len(files) > bulk_limit:
            bulk += 1          # a vendor-bump or bulk import, not authorship
            continue
        p = people[ae.lower().strip()]
        p["commits"] += 1
        p["files"] += len(files)
        p["names"].add(an)
        if p["first"] is None or aI < p["first"]:
            p["first"] = aI
        if p["last"] is None or aI > p["last"]:
            p["last"] = aI
        if len(p["examples"]) < 2:
            p["examples"].append(subj[:70])
    return people, total, bulk


def run(repo, sampled, skip_shared=False):
    """skip_shared=True for very large repos: pickaxe on a blobless clone fetches
    blobs one at a time over the network and does not finish (pytorch's 11 shared
    files ran >25 min). Use a full clone there, or take dedicated files only."""
    print(f"\n=== {repo} ===", flush=True)
    d = clone(repo)
    if not d:
        print("    CLONE FAILED")
        return None
    ap = tree_paths(d)
    cp = content_paths(repo)
    kept, vend, bund = pick_paths(ap, sampled, cp)
    print(f"    tree files={len(ap)}  grep hits={len(cp)}  kept={len(kept)} "
          f"vendored={len(vend)} bundled={len(bund)}", flush=True)
    dedicated = [p for p in kept if HALIDE_RE.search(p)]
    shared = [] if skip_shared else [p for p in kept if not HALIDE_RE.search(p)]
    people, tot_d, bulk_d = log_authors(d, dedicated)
    people, tot_s, bulk_s = log_authors(d, shared, pickaxe=True, people=people)
    print(f"    commits: {tot_d} dedicated + {tot_s} halide-touching on shared")
    rows = sorted(people.items(), key=lambda kv: -kv[1]["commits"])
    return {"repo": repo, "n_paths": len(kept), "n_dedicated": len(dedicated),
            "n_shared": len(shared), "paths": kept, "vendored_paths": len(vend),
            "bundled_paths": len(bund), "n_commits": tot_d + tot_s,
            "bulk_skipped": bulk_d + bulk_s, "skip_shared": skip_shared,
            "people": [{"email": ae, "names": sorted(v["names"]), "commits": v["commits"],
                        "files": v["files"],
                        "first": v["first"][:10] if v["first"] else None,
                        "last": v["last"][:10] if v["last"] else None,
                        "examples": v["examples"]} for ae, v in rows]}


def fork_authors(repo):
    """An extending fork carries all of Halide's history, so a plain log credits
    Adams with the whole thing. Excluding halide/Halide is NOT enough either:
    Halide's git history was REWRITTEN (halide/Halide_old_history exists), so the
    fork's base commits are unreachable from current upstream and still read as
    the fork's own. Both remotes must be excluded.

    jrk/gradient-halide, measured:
      no exclusion            Adams 11,454 / Johnson 4,586 / Sharlet 4,102
      --not halide/Halide     Adams  5,659   <- still wrong
      --not BOTH              444 commits: Tzu-Mao Li 247, Michael Gharbi 77
    """
    d = clone(repo)
    for name, url in (("up", "https://github.com/halide/Halide.git"),
                      ("old", "https://github.com/halide/Halide_old_history.git")):
        sh(["git", "remote", "add", name, url], cwd=d)
        sh(["git", "fetch", "--quiet", "--filter=blob:none", name,
            f"refs/heads/*:refs/remotes/{name}/*"], cwd=d, timeout=1800)
    r = sh(["git", "log", "--format=%an\x02%ae", "HEAD",
            "--not", "--remotes=up", "--remotes=old"], cwd=d, timeout=1800)
    people = defaultdict(lambda: {"commits": 0, "names": set()})
    for line in r.stdout.splitlines():
        if "\x02" not in line:
            continue
        an, ae = line.split("\x02", 1)
        p = people[ae.lower().strip()]
        p["commits"] += 1
        p["names"].add(an)
    rows = sorted(people.items(), key=lambda kv: -kv[1]["commits"])
    return {"repo": repo, "mode": "fork_excluding_halide_and_halide_old_history",
            "n_commits": sum(v["commits"] for _, v in rows),
            "people": [{"email": ae, "names": sorted(v["names"]),
                        "commits": v["commits"]} for ae, v in rows]}


if __name__ == "__main__":
    pool = json.load(open("data/pools/lane_b_classified.json"))
    idx = {x["repo"]: x for x in pool["repos"]}
    out = []
    for t in sys.argv[1:]:
        if t.startswith("fork:"):
            out.append(fork_authors(t[5:]))
        else:
            big = t.endswith("!")
            t = t.rstrip("!")
            res = run(t, idx.get(t, {}).get("paths", []), skip_shared=big)
            if res:
                out.append(res)
    print(json.dumps({"schema_version": 1, "status": "unintegrated",
                      "n_repos": len(out), "repos": out}, indent=1))
