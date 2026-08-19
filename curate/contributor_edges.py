#!/usr/bin/env python3
"""Turn the contributor harvest into person nodes and stamped contribution edges.

The second half of the contributor lane, per his 2026-08-19 split. The harvest
(contributor_harvest.py) is expensive and role-free; this is cheap and carries
the judgement, so it re-runs whenever the judged pass refines a repo's role or
the harvest improves. Nothing here re-clones anything.

CATEGORIES (his ruling, amending the earlier "inherit the repo's role"):

    core       halide/Halide itself
    extends    the fork_diff extending forks -- someone modified Halide
    packaging  the distribution trees; a ports maintainer bumping a version
               is not a Halide user
    uses       everything else, the default

All four are decided from data already in the repo, so this does not wait on the
judged pass. That pass refines only WITHIN `uses` (a repo may later read as a
descendant), which changes no edge already written -- it only makes a coarse
label finer. A person on a not-yet-judged repo reads `uses`: imprecise, never
wrong.

MERGING. The anchor's 227 people and the harvest's 893 emails are the same
population seen twice, so they are merged in ONE union-find rather than joined
afterwards -- Andrew Adams commits to halide/Halide and to fourteen other repos,
and a join keyed on anything less than the anchor's own rules would split him.
The rules come from contributors.py unchanged (email, normalised name, GitHub
noreply handle, email local-part; placeholders and generic local-parts denied),
because they were tuned against this exact history and re-deriving them here
would be a second, subtly different answer to a solved problem.

Over-merging stays worse than under-merging: a split person is visible and
fixable, while one person wearing another's commits looks entirely plausible in
a chart.

BOTS are excluded from person nodes and RECORDED (ruling 11). Both bot rules
apply -- contributors.py's and the harvest's -- because they were written for
different populations and each catches what the other misses.

Usage:
  python3 -u curate/contributor_edges.py
"""
import argparse, json, os, subprocess, sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import contributors as ca                       # the anchor's merge rules

ANCHOR = "halide/Halide"


def bootstrap_anchor(path, clone_dir):
    """The anchor's 227 people are not in the repo -- contributors.py needs a
    clone. A blobless bare one is 27MB, so rebuild rather than fail."""
    if os.path.exists(path):
        return
    if not os.path.isdir(clone_dir):
        print(f"no {path} -- cloning halide/Halide blobless (~27MB)")
        subprocess.run(["git", "clone", "--bare", "--filter=blob:none", "--quiet",
                        f"https://github.com/{ANCHOR}.git", clone_dir], check=True)
    here = os.path.dirname(os.path.abspath(__file__))
    subprocess.run([sys.executable, "-u", os.path.join(here, "contributors.py"),
                    "--repo", clone_dir, "--out", path], check=True)


def repo_category(slug, forks, statuses):
    if slug == ANCHOR:
        return "core"
    if slug in forks:
        return "extends"
    if statuses.get(slug) == "packaging":
        return "packaging"
    return "uses"


def is_bot(name, email):
    """Union of both rules. contributors.py's was written against the anchor's
    nightly builders; the harvest's against CI accounts in other people's repos.
    Neither is a superset of the other."""
    import contributor_harvest as ch
    if ca.BOTS.search(name or "") or ca.BOTS.search(email or ""):
        return "anchor_bot_rule"
    rule, _ = ch.bot_flag(email or "", [name] if name else [])
    return rule


def collect(harvest, anchor):
    """Every (name, email, commits, repo) observation, from both sources."""
    obs = []
    for p in anchor["people"]:
        names = [p["name"]] + p.get("aliases", [])
        for e in p["emails"]:
            obs.append({"name": p["name"], "email": e.lower().strip(),
                        "names": names, "repo": ANCHOR,
                        "commits": p["commits"] if e == p["emails"][0] else 0,
                        "share": None,
                        "first": p.get("first_commit"), "last": p.get("last_commit")})
    for r in harvest["repos"]:
        if r.get("status") != "ok":
            continue
        for p in r.get("people", []):
            names = p.get("names") or []
            obs.append({"name": names[0] if names else "",
                        "email": p["email"].lower().strip(), "names": names,
                        "repo": r["repo"], "commits": p.get("commits", 0),
                        "share": p.get("share"),
                        "first": p.get("first"), "last": p.get("last")})
    return obs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--harvest", default="data/pools/contributor_harvest.json")
    ap.add_argument("--anchor", default="data/people/halide_contributors.json")
    ap.add_argument("--clone", default="/tmp/clones/Halide.git")
    ap.add_argument("--curatable", default="data/pools/lane_b_curatable.json")
    ap.add_argument("--forks", default="data/pools/fork_verdicts.json")
    ap.add_argument("--aliases", default="data/pools/person_aliases.json")
    ap.add_argument("--out", default="data/pools/contributor_edges.json")
    args = ap.parse_args()
    sys.stdout.reconfigure(line_buffering=True)

    bootstrap_anchor(args.anchor, args.clone)
    harvest = json.load(open(args.harvest))
    anchor = json.load(open(args.anchor))

    forks = {r["repo"] for r in json.load(open(args.forks))["repos"]
             if r.get("verdict") == "extending_fork"}
    statuses = {r["repo"]: r.get("status")
                for r in json.load(open(args.curatable))["repos"]}

    repo_totals = {r["repo"]: r.get("n_commits") or 0
                   for r in harvest["repos"] if r.get("status") == "ok"}
    repo_totals[ANCHOR] = anchor.get("n_commits") or sum(
        p["commits"] for p in anchor["people"])

    obs = collect(harvest, anchor)
    print(f"{len(obs)} identity observations "
          f"({len(anchor['people'])} anchor people, "
          f"{harvest['n_identities']} harvest slots)")

    # One union-find over both populations, with the anchor's rules.
    uf = ca.UnionFind()
    for o in obs:
        ident = ("id", o["name"], o["email"])
        uf.union(ident, ("email", o["email"]))
        for n in o["names"] or [o["name"]]:
            norm = ca.normalize_name(n)
            if norm and norm not in ca.PLACEHOLDER_NAMES:
                uf.union(ident, ("name", norm))
        handle = ca.NOREPLY.match(o["email"])
        if handle:
            uf.union(ident, ("gh", handle.group(1).lower()))
        else:
            local = o["email"].split("@")[0]
            if len(local) >= 4 and local not in ca.GENERIC_LOCALPARTS:
                uf.union(ident, ("localpart", local))

    people = defaultdict(lambda: {"names": Counter(), "emails": set(),
                                  "repos": {}, "first": None, "last": None,
                                  "bot_rules": set()})
    for o in obs:
        key = uf.find(("id", o["name"], o["email"]))
        p = people[key]
        for n in o["names"] or [o["name"]]:
            if n:
                p["names"][n] += 1
        p["emails"].add(o["email"])
        rule = is_bot(o["name"], o["email"])
        if rule:
            p["bot_rules"].add(rule)
        slot = p["repos"].setdefault(o["repo"], {"commits": 0})
        slot["commits"] += o["commits"]
        for k, cmp in (("first", min), ("last", max)):
            if o[k]:
                p[k] = o[k] if p[k] is None else cmp(p[k], o[k])

    # Cross-layer author ids, from the hand-reviewed alias file only. The
    # initial-only key is never automated (his ruling).
    alias = json.load(open(args.aliases))
    email_to_author = {}
    for a in alias.get("contributor_aliases", []):
        for g in a.get("git", []):
            if "<" in g and ">" in g:
                email_to_author[g.split("<", 1)[1].rstrip(">").lower()] = a["author"]

    nodes, edges, bots = [], [], []
    for i, (key, p) in enumerate(sorted(people.items(),
                                        key=lambda kv: -sum(r["commits"] for r in kv[1]["repos"].values()))):
        display = p["names"].most_common(1)[0][0] if p["names"] else sorted(p["emails"])[0]
        total = sum(r["commits"] for r in p["repos"].values())
        author = next((email_to_author[e] for e in p["emails"] if e in email_to_author), None)
        rec = {"person_id": f"git:{i:04d}", "name": display,
               "aliases": sorted(n for n in p["names"] if n != display),
               "emails": sorted(p["emails"]), "n_repos": len(p["repos"]),
               "commits": total, "first": p["first"], "last": p["last"],
               "author_id": author}
        if p["bot_rules"]:
            rec["bot_rules"] = sorted(p["bot_rules"])
            bots.append(rec)                     # recorded, not silently dropped
            continue
        nodes.append(rec)
        for slug, slot in sorted(p["repos"].items()):
            # Recomputed here, never carried from the harvest: two of a person's
            # emails in one repo are two harvest rows, and taking the share off
            # either one understates a merged person by exactly the other's work.
            denom = repo_totals.get(slug) or 0
            edges.append({"person_id": rec["person_id"], "repo": slug,
                          "category": repo_category(slug, forks, statuses),
                          "commits": slot["commits"],
                          "share": round(slot["commits"] / denom, 4) if denom else None})

    cats = Counter(e["category"] for e in edges)
    doc = {"schema_version": 1, "n_people": len(nodes), "n_edges": len(edges),
           "n_bots_excluded": len(bots), "categories": dict(cats),
           "n_with_author_id": sum(1 for n in nodes if n["author_id"]),
           "people": nodes, "edges": edges, "bots": bots}
    json.dump(doc, open(args.out, "w"), indent=1)

    print(f"{len(nodes)} people, {len(edges)} edges, {len(bots)} bots excluded")
    print(f"  categories: {dict(cats)}")
    print(f"  joined to an author id: {doc['n_with_author_id']}")
    multi = [n for n in nodes if n["n_repos"] > 1]
    print(f"  in more than one repo: {len(multi)}")
    print(f"\n{'person':28s} {'repos':>5s} {'commits':>8s}")
    for n in nodes[:15]:
        print(f"{n['name'][:28]:28s} {n['n_repos']:5d} {n['commits']:8d}")
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
