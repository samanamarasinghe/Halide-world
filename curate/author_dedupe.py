#!/usr/bin/env python3
"""Propose merges for person records that share a name but hold different author ids.

Semantic Scholar issues several author ids to one human, so the person layer carries the
same name many times over -- Yun Liang 7 records, Tianqi Chen 6. A contributor joining
"on the name" therefore joins one of several, which is why this must run WITH the
cross-layer merge in data/pools/person_aliases.json rather than after it.

The evidence is SHARED COAUTHORS. Two ids of one person never appear on the same paper,
but their papers reach the same collaborators, so an overlap between two same-named
records' coauthor sets is positive evidence they are one human. A name match alone is not,
and is never enough here.

    ONE HARD VETO: if two same-named records appear on the SAME paper, they are not merged
    at any threshold. Either they are two different people, or the source duplicated one
    author within one author list; both cases need a human, and the coauthor rule would
    otherwise merge them confidently -- the one such case in this data is also the group
    with the MOST shared coauthors, so the veto is not hypothetical.

No-evidence is not counter-evidence. A record holding one paper may simply have no
observable overlap, so an unmerged group means "not shown to be the same", not "shown to
be different". Under-merging stays the safe direction: a split person is visible and
fixable, a wrongly merged one is not.

    python3 curate/author_dedupe.py --index data/site/halide-index.json
    python3 curate/author_dedupe.py --threshold 2 --out data/pools/author_dedupe.json
"""
import argparse
import collections
import itertools
import json


def load(path):
    with open(path) as f:
        data = json.load(f)
    papers, people = {}, []
    for e in data.get("entries", []):
        if e.get("kind") in ("paper", "anchor"):
            papers[e["id"]] = e
        elif e.get("kind") == "person":
            people.append(e)
    return papers, people


def coauthors(people, papers):
    out = collections.defaultdict(set)
    for p in people:
        for w in p.get("papers") or []:
            pa = papers.get(w)
            if pa:
                out[p["id"]] |= set(pa.get("author_ids") or []) - {p["id"]}
    return out


def cooccurring(name_ids, papers):
    """Names whose records share an author list -- the hard veto."""
    veto = {}
    for name, ids in name_ids.items():
        s = set(ids)
        for pa in papers.values():
            both = set(pa.get("author_ids") or []) & s
            if len(both) > 1:
                veto[name] = {"paper": pa.get("title"), "ids": sorted(both)}
                break
    return veto


def n_works(p):
    return len(p.get("papers") or []) + len(p.get("anchor_papers") or [])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", default="data/site/halide-index.json")
    ap.add_argument("--threshold", type=int, default=2,
                    help="minimum shared coauthors between two records to merge them")
    ap.add_argument("--out", help="write the proposal as JSON")
    args = ap.parse_args()

    papers, people = load(args.index)
    byid = {p["id"]: p for p in people}
    coa = coauthors(people, papers)

    groups = collections.defaultdict(list)
    for p in people:
        groups[p["name"]].append(p["id"])
    dups = {n: ids for n, ids in groups.items() if len(ids) > 1}
    veto = cooccurring(dups, papers)

    proposals, removed = [], 0
    for name, ids in sorted(dups.items()):
        if name in veto:
            continue
        parent = {i: i for i in ids}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        best = 0
        for a, b in itertools.combinations(ids, 2):
            n = len(coa[a] & coa[b])
            best = max(best, n)
            if n >= args.threshold:
                ra, rb = find(a), find(b)
                if ra != rb:
                    parent[ra] = rb
                    removed += 1
        clusters = collections.defaultdict(list)
        for i in ids:
            clusters[find(i)].append(i)
        for members in clusters.values():
            if len(members) > 1:
                # the record with the most works keeps the node
                keep = max(members, key=lambda i: n_works(byid[i]))
                proposals.append({
                    "name": name,
                    "keep": keep,
                    "merge": [i for i in members if i != keep],
                    "shared_coauthors": best,
                    "works": {i: n_works(byid[i]) for i in members},
                })

    one_work = sum(1 for ids in dups.values() if all(n_works(byid[i]) == 1 for i in ids))
    print(f"duplicate-name groups: {len(dups)}  ({sum(len(v) for v in dups.values())} person records)")
    print(f"vetoed by co-occurrence on one paper: {len(veto)}")
    for n, v in veto.items():
        print(f"  - {n}: {v['ids']} both on {v['paper'][:60]!r}")
    print(f"proposed merges at >={args.threshold} shared coauthors: "
          f"{len(proposals)} clusters, {removed} records disappear")
    print(f"groups where every record holds one work: {one_work} "
          f"-- no overlap is observable either way; left split")

    if args.out:
        with open(args.out, "w") as f:
            json.dump({"threshold": args.threshold, "vetoed": veto,
                       "proposals": proposals}, f, indent=1)
        print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
