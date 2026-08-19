#!/usr/bin/env python3
"""Run repo_contributors.py over the whole repo pool. HARVEST ONLY -- no roles.

His 2026-08-19 ruling split the contributor lane in two. This is the first half:
repo -> people + commit counts, with no category stamped. The second half
(contributor_edges.py) stamps core/extends/packaging/uses and is cheap enough to
re-run whenever curation refines the `uses` bucket. Keeping them apart is what
makes the expensive half runnable before the judged pass lands.

Disk is the binding constraint, not time: the 8-repo pilot left 1.6GB, so both
clones are deleted the moment a repo's record is written. Peak stays at one repo.

Resumable by construction. The checkpoint is written after EVERY repo, so a run
killed at repo 400 resumes at 400. Re-running with no arguments is a no-op over
what is already done -- that is the point, since this lane adds hundreds of
people to a person layer that has already merged and will be re-run.

Two modes, chosen per repo:
  fork_excl -- the 8 fork_diff extending forks. A plain log credits Adams with
               Halide's whole history; fork_authors() excludes both upstream
               remotes (the history rewrite means one is not enough).
  path_log  -- everything else. Dedicated paths by log, shared paths by pickaxe.

BIG REPOS: pickaxe on a blobless clone fetches ONE BLOB PER COMMIT touching a
shared path, so it does not finish on deep histories (pytorch's 11 shared files
ran >25 min). --shared-budget caps the count of such commits, which `rev-list
--count` gives for free; over it, the repo takes dedicated paths only and is
stamped shared_skipped. A count is a stable, explainable omission. A wall-clock
timeout is not, and nothing downstream may key on one (the fork_diff
`fetch_timeout` lesson).

BOTS are flagged, never dropped (ruling 11). The edge pass decides what to do
with them; a silently missing identity cannot be audited.

Usage:
  python3 -u curate/contributor_harvest.py --limit 20 --sample stratified
  python3 -u curate/contributor_harvest.py            # the full pool, resumable
"""
import argparse, json, os, re, shutil, subprocess, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import repo_contributors as rc

BOT_RULES = [
    (re.compile(r"\[bot\]", re.I), "name_bot_tag"),
    (re.compile(r"\bbot\b", re.I), "name_bot_word"),
    (re.compile(r"dependabot|renovate|greenkeeper|github-actions|mergebot|"
                r"codecov|snyk|travis|appveyor|jenkins", re.I), "known_ci_bot"),
    (re.compile(r"^\d+\+?[\w.-]*bot[\w.-]*@users\.noreply\.github\.com$", re.I), "noreply_bot"),
]


def bot_flag(email, names):
    """Return (rule, matched_on) or (None, None). Checked against every display
    name the identity used, because one email can carry several."""
    for rx, rule in BOT_RULES:
        if rx.search(email):
            return rule, email
        for n in names:
            if rx.search(n):
                return rule, n
    return None, None


def ensure_pool(pool, meta):
    """Rebuild the curatable list rather than fail. It is built from
    repo_meta_state.json, which is gitignored, so a fresh clone has neither --
    the recurring trap in this project is a pipeline input that lives on one
    disk. Rebuilding costs ~6 min against ecosyste.ms and reproduces the counts
    exactly (anchor 1, curatable 552, drop 102, packaging 12). Same principle as
    admit_artifact_repos.py fetching in-script: the output must regenerate from
    the repo alone.

    contributor_edges.py calls this too. One bootstrap, not two that drift."""
    if os.path.exists(pool):
        return
    here = os.path.dirname(os.path.abspath(__file__))
    if not os.path.exists(meta):
        print(f"no {meta} -- running enrich_repos.py (~6 min)", flush=True)
        subprocess.run([sys.executable, "-u", os.path.join(here, "enrich_repos.py"),
                        "--out", meta], check=True)
    print(f"no {pool} -- running cleanup_repos.py", flush=True)
    subprocess.run([sys.executable, "-u", os.path.join(here, "cleanup_repos.py"),
                    "--meta", meta, "--out", pool], check=True)


def load_pool(args):
    """The repo list, plus the sampled Lane B paths each run() needs.

    lane_b_curatable.json is cleanup_repos.py's output and is not in the repo,
    because it depends on the gitignored repo_meta_state.json. Both are rebuilt
    here when missing, so the lane starts from a bare clone."""
    ensure_pool(args.pool, args.meta)
    doc = json.load(open(args.pool))
    rows = doc["repos"] if isinstance(doc, dict) else doc
    keep = set(args.statuses.split(","))
    pool = [r for r in rows if r.get("status") in keep]

    classified = {x["repo"]: x for x in
                  json.load(open(args.classified))["repos"]}
    forks = set()
    if os.path.exists(args.forks):
        forks = {r["repo"] for r in json.load(open(args.forks))["repos"]
                 if r.get("verdict") == "extending_fork"}

    out = []
    for r in pool:
        slug = r["repo"] if isinstance(r, dict) else r
        m = (r.get("meta") or {}) if isinstance(r, dict) else {}
        out.append({"repo": slug,
                    "sampled": classified.get(slug, {}).get("paths", []),
                    "stars": m.get("stargazers_count") or 0,
                    "is_fork": slug in forks})
    return out


def stratify(pool, n):
    """Load the boundaries, not a random draw: the forks, the biggest repos, the
    ones with no sampled paths at all, and a spread of ordinary ones. Agreement
    on a stratified pilot is NOT an accuracy estimate -- the curation pilot made
    that mistake once and it is worth not repeating."""
    picked, seen = [], set()

    def take(rows, k):
        for r in rows:
            if len(picked) >= n or r["repo"] in seen:
                continue
            if k and sum(1 for p in picked if p["_stratum"] == k) >= n // 4:
                return
            r = dict(r, _stratum=k)
            picked.append(r)
            seen.add(r["repo"])

    take([r for r in pool if r["is_fork"]], "fork")
    take(sorted(pool, key=lambda r: -r["stars"]), "big")
    take([r for r in pool if not r["sampled"]], "no_sampled_paths")
    step = max(1, len(pool) // max(1, n))
    take(pool[::step], "ordinary")
    take(pool, "ordinary")
    return picked[:n]


def harvest_one(row, shared_budget):
    t0 = time.time()
    slug = row["repo"]
    try:
        if row["is_fork"]:
            rec = rc.fork_authors(slug)
            rec["mode"] = "fork_excl"
            rec["shared_skipped"] = False
        else:
            rec = rc.run(slug, row["sampled"], shared_budget=shared_budget)
            if rec is None:
                return {"repo": slug, "status": "clone_failed"}
            rec["mode"] = "path_log"
            rec["shared_skipped"] = bool(rec.get("skip_shared"))
    except Exception as e:                      # a bad repo must not kill the run
        return {"repo": slug, "status": "error", "error": f"{type(e).__name__}: {e}"[:300]}

    total = rec.get("n_commits") or 0
    for p in rec.get("people", []):
        rule, on = bot_flag(p["email"], p.get("names", []))
        p["is_bot"] = bool(rule)
        if rule:
            p["bot_rule"], p["bot_matched_on"] = rule, on
        # his granular ask: how much of the repo's Halide work this person did
        p["share"] = round(p["commits"] / total, 4) if total else None

    rec["status"] = "ok"
    rec["stars"] = row["stars"]
    rec["stratum"] = row.get("_stratum")
    rec["n_people"] = len(rec.get("people", []))
    rec["n_bots"] = sum(1 for p in rec.get("people", []) if p["is_bot"])
    rec["seconds"] = round(time.time() - t0, 1)
    return rec


def cleanup_clones(slug):
    """Delete both clones NOW. 552 repos at pilot rates is hundreds of GB."""
    freed = 0
    for d in (os.path.join(rc.WORK, slug.replace("/", "__")),
              os.path.join(rc.WORK, "shallow__" + slug.replace("/", "__"))):
        if os.path.isdir(d):
            for root, _, files in os.walk(d):
                for f in files:
                    try:
                        freed += os.path.getsize(os.path.join(root, f))
                    except OSError:
                        pass
            shutil.rmtree(d, ignore_errors=True)
    return freed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", default="data/pools/lane_b_curatable.json")
    ap.add_argument("--meta", default="data/pools/repo_meta_state.json")
    ap.add_argument("--classified", default="data/pools/lane_b_classified.json")
    ap.add_argument("--forks", default="data/pools/fork_verdicts.json")
    ap.add_argument("--state", default="data/pools/contributor_harvest_state.json")
    ap.add_argument("--out", default="data/pools/contributor_harvest.json")
    # The anchor is NOT in the default set. halide/Halide's 227 people come from
    # curate/contributors.py over its whole history; running it through here
    # restricts it to Halide-named paths and reports 46 people / 545 commits,
    # which is not wrong so much as a different question.
    ap.add_argument("--statuses", default="curatable,packaging")
    ap.add_argument("--shared-budget", type=int, default=1500,
                    help="commits touching the shared paths above which the "
                         "pickaxe pass is skipped; each one costs a blob fetch")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--sample", choices=["head", "stratified"], default="head")
    ap.add_argument("--only", help="comma-separated slugs, ignores the pool order")
    ap.add_argument("--redo", action="store_true", help="ignore the checkpoint")
    args = ap.parse_args()
    sys.stdout.reconfigure(line_buffering=True)   # else nohup logs look hung

    pool = load_pool(args)
    if args.only:
        want = set(args.only.split(","))
        pool = [r for r in pool if r["repo"] in want]
    state = {} if args.redo or not os.path.exists(args.state) else \
        json.load(open(args.state))
    todo = [r for r in pool if r["repo"] not in state]
    if args.limit:
        todo = stratify(todo, args.limit) if args.sample == "stratified" \
            else todo[:args.limit]

    print(f"pool {len(pool)}  done {len(state)}  this run {len(todo)}")
    freed = 0
    for i, row in enumerate(todo, 1):
        print(f"[{i}/{len(todo)}] {row['repo']} "
              f"({row.get('_stratum','-')}, {row['stars']} stars)")
        rec = harvest_one(row, args.shared_budget)
        freed += cleanup_clones(row["repo"])
        state[rec["repo"]] = rec
        json.dump(state, open(args.state, "w"), indent=1)   # after EVERY repo
        print(f"    {rec['status']}  people={rec.get('n_people','-')} "
              f"commits={rec.get('n_commits','-')} bots={rec.get('n_bots','-')} "
              f"{rec.get('seconds','-')}s  freed={freed/1e9:.1f}GB total")

    rows = sorted(state.values(), key=lambda r: r["repo"])
    ok = [r for r in rows if r["status"] == "ok"]
    doc = {"schema_version": 1, "status": "harvest_only_no_roles",
           "n_repos": len(rows), "n_ok": len(ok),
           "n_failed": len(rows) - len(ok),
           "n_identities": sum(r.get("n_people", 0) for r in ok),
           "n_bot_identities": sum(r.get("n_bots", 0) for r in ok),
           "shared_budget": args.shared_budget, "repos": rows}
    json.dump(doc, open(args.out, "w"), indent=1)
    print(f"\nwrote {args.out}: {len(ok)} ok, {len(rows)-len(ok)} failed, "
          f"{doc['n_identities']} identities ({doc['n_bot_identities']} bot)")


if __name__ == "__main__":
    main()
