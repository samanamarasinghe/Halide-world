"""Enrich Lane B repo candidates with GitHub metadata, keylessly.

The GitHub REST API allows 60 requests/hour unauthenticated, which is not
enough for 661 repos. Two keyless routes cover it instead:

  repos.ecosyste.ms   description, stars, forks, language, fork flag,
                      archived flag, topics, license, created/pushed dates
  raw.githubusercontent.com   the README

Measured on a 20-repo sample: metadata 0.44 s/repo, README 1.5 s/repo
(the README costs more because it probes master/main x four filenames).
The full 661 is roughly 5 minutes of metadata and 17 minutes of READMEs.

Results are written to their own state file. The pool is never rewritten.

    python3 curate/enrich_repos.py --pool data/pools/lane_b_classified.json \
        --out data/pools/repo_meta_state.json [--readme] [--limit N]
"""
import argparse, json, os, sys, time, urllib.error, urllib.request

sys.stdout.reconfigure(line_buffering=True)

UA = {"User-Agent": "halide-world-index/0.1 (research index; contact via repo)"}
ECOSYSTEMS = "https://repos.ecosyste.ms/api/v1/hosts/GitHub/repositories/{}"
RAW = "https://raw.githubusercontent.com/{repo}/{branch}/{name}"
BRANCHES = ("master", "main")
READMES = ("README.md", "readme.md", "README.rst", "README")
# Kept fields. `fork` and `source_name` matter most: the fork-candidate
# detector ran over 8 repos chosen by signature profile and missed forks
# that the fork flag names outright.
FIELDS = ("full_name", "description", "stargazers_count", "forks_count",
          "subscribers_count", "language", "fork", "source_name", "archived",
          "topics", "license", "created_at", "pushed_at", "size", "owner")
README_CAP = 4000   # enough to judge role; whole READMEs are not worth storing


def get(url, timeout=25):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA),
                                  timeout=timeout).read()


def fetch_meta(repo):
    try:
        d = json.loads(get(ECOSYSTEMS.format(repo)))
        return {k: d.get(k) for k in FIELDS}
    except urllib.error.HTTPError as e:
        return {"error": f"http {e.code}"}
    except Exception as e:
        return {"error": str(e)[:120]}


def fetch_readme(repo):
    for branch in BRANCHES:
        for name in READMES:
            try:
                txt = get(RAW.format(repo=repo, branch=branch, name=name),
                          timeout=15).decode("utf-8", "replace")
                return txt[:README_CAP]
            except Exception:
                continue
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", default="data/pools/lane_b_classified.json")
    ap.add_argument("--out", default="data/pools/repo_meta_state.json")
    ap.add_argument("--verdicts", default="uses_source,consumer,generator",
                    help="comma-separated verdicts to enrich")
    ap.add_argument("--readme", action="store_true", help="also fetch READMEs")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--sleep", type=float, default=0.15)
    args = ap.parse_args()

    wanted = set(args.verdicts.split(","))
    repos = [r["repo"] for r in json.load(open(args.pool))["repos"]
             if r["verdict"] in wanted]
    if args.limit:
        repos = repos[:args.limit]

    # Resume: an interrupted run keeps everything it already fetched.
    state = json.load(open(args.out)) if os.path.exists(args.out) else {}
    todo = [r for r in repos
            if r not in state or (args.readme and "readme" not in state[r])]
    print(f"{len(repos)} repos in scope, {len(todo)} to fetch")

    t0 = time.time()
    for i, repo in enumerate(todo, 1):
        rec = state.get(repo) or fetch_meta(repo)
        if args.readme and "readme" not in rec:
            rec["readme"] = fetch_readme(repo)
        state[repo] = rec
        if i % 25 == 0 or i == len(todo):
            json.dump(state, open(args.out, "w"), indent=1)
            print(f"  {i}/{len(todo)}  {time.time()-t0:.0f}s")
        time.sleep(args.sleep)

    json.dump(state, open(args.out, "w"), indent=1)
    errs = sum(1 for v in state.values() if "error" in v)
    desc = sum(1 for v in state.values() if v.get("description"))
    rdme = sum(1 for v in state.values() if v.get("readme"))
    print(f"wrote {args.out}: {len(state)} repos, {errs} errors, "
          f"{desc} with a description, {rdme} with a README")


if __name__ == "__main__":
    main()
