"""Author-layer dedupe — collapse the S2 author ids that are the same human.

S2 over-splits authors and never conflates them: 5,214 distinct names carry
5,688 ids, 362 names hold more than one id, and NO id holds more than one name
spelling. So the id is a safe atom and the only question is whether two ids
under the same name are one person.

His ruling of 2026-08-19: resolve with a SECOND SIGNAL, no hand review.

Evidence, in order of strength:
  paper     the two ids appear on the same paper
  coauthor  their coauthor NAME sets intersect. Keyed on name, never on id --
            an id key is degraded by the very splitting it is meant to fix,
            because the coauthor is split too (name-keyed links 251 groups
            where id-keyed links 218)
  2-hop     one id's coauthors, expanded one hop through the global coauthor
            graph, reach the other's. MEASURED against a control of random
            different-name id pairs: 17% on target vs 4% on control. Real but
            thin -- it settles 22 further groups, among them Andrew Adams
            (3 ids, all genuinely his) and Frédo Durand (2)

Signals measured and REJECTED as non-discriminative: shared venue (9% target /
5% control) and shared field of study (98% / 97% -- almost every record is
"Computer Science").

A group merges only if EVERY pair inside it is linked. Requiring a clique is
the whole point: linking A-B and B-C does not make A and C the same person, and
merging is transitive, which is how `unknown` once chained four different
halide/Halide contributors into one node.

What cannot be settled is LEFT SPLIT and tagged, never guessed. Over-merging is
worse than under-merging: a split person is visible and fixable, a falsely
merged one is not. THE COST IS REAL AND SHOULD NOT BE HIDDEN -- 143 groups stay
split, and some are obviously one person (Christophe Dubach, two ids with 1 and
17 papers and no shared coauthor at all; Michel Steuwer 2/3 pairs; Albert Cohen
5/6). Affiliation strings are the next signal for exactly these.

    python3 curate/author_dedupe.py --out data/pools/author_dedupe.json
"""
import argparse, collections, itertools, json, sys

sys.stdout.reconfigure(line_buffering=True)


def build(works):
    co = collections.defaultdict(set)      # id -> coauthor NAMES
    papers = collections.defaultdict(set)  # id -> paper ids
    name_ids = collections.defaultdict(set)
    nbr = collections.defaultdict(set)     # global coauthor graph, name -> names
    for pid, w in works.items():
        names = [(a.get("name") or "").strip()
                 for a in (w.get("authors") or []) if a.get("name")]
        for x in names:
            nbr[x] |= set(names) - {x}
        for a in (w.get("authors") or []):
            i, n = a.get("s2_author_id"), (a.get("name") or "").strip()
            if not i or not n:
                continue
            name_ids[n].add(i)
            papers[i].add(pid)
            co[i] |= set(names) - {n}
    return co, papers, name_ids, nbr


def evidence(a, b, co, papers, nbr):
    if papers[a] & papers[b]:
        return "paper"
    if co[a] & co[b]:
        return "coauthor"
    expanded = set(co[a])
    for x in co[a]:
        expanded |= nbr[x]
    if expanded & co[b]:
        return "2-hop"
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--papers", default="data/pools/lane_a.json")
    ap.add_argument("--out", default="data/pools/author_dedupe.json")
    args = ap.parse_args()

    works = json.load(open(args.papers))["works"]
    co, papers, name_ids, nbr = build(works)
    multi = {n: sorted(ids) for n, ids in name_ids.items() if len(ids) > 1}
    print(f"{len(name_ids)} names, {sum(len(v) for v in name_ids.values())} ids, "
          f"{len(multi)} names with more than one id")

    merged, split = [], []
    counts = collections.Counter()
    for n, ids in sorted(multi.items()):
        pairs = list(itertools.combinations(ids, 2))
        ev = {p: evidence(p[0], p[1], co, papers, nbr) for p in pairs}
        if all(ev.values()):
            strongest = "paper" if "paper" in ev.values() else (
                "2-hop" if "2-hop" in ev.values() else "coauthor")
            merged.append({"name": n, "ids": ids, "canonical_id": max(
                ids, key=lambda i: len(papers[i])),
                "n_papers": {i: len(papers[i]) for i in ids},
                "evidence": strongest,
                "pair_evidence": {f"{a}+{b}": v for (a, b), v in ev.items()}})
            counts["merged_" + strongest] += 1
        else:
            split.append({"name": n, "ids": ids,
                          "n_papers": {i: len(papers[i]) for i in ids},
                          "linked_pairs": sum(1 for v in ev.values() if v),
                          "total_pairs": len(pairs),
                          "reason": "no evidence links every pair; left split "
                                    "rather than guessed"})
            counts["left_split"] += 1

    ids_removed = sum(len(m["ids"]) - 1 for m in merged)
    print(f"\n  merged on a shared paper     : {counts['merged_paper']}")
    print(f"  merged on a shared coauthor  : {counts['merged_coauthor']}")
    print(f"  merged via the 2-hop signal  : {counts['merged_2-hop']}")
    print(f"  LEFT SPLIT, tagged           : {counts['left_split']}")
    print(f"  author ids collapsed away    : {ids_removed}")

    json.dump({"schema_version": 1,
               "note": ("Author-layer dedupe. A group merges only when EVERY "
                        "pair in it is linked. Unsettled groups are LEFT SPLIT "
                        "and tagged, never guessed -- affiliation strings are "
                        "the next signal for them."),
               "signals_rejected": {"shared_venue": "9% target vs 5% control",
                                    "shared_field": "98% vs 97%, non-discriminative"},
               "two_hop_discrimination": "17% target vs 4% control",
               "n_merged": len(merged), "n_left_split": len(split),
               "ids_collapsed": ids_removed,
               "merged": merged, "left_split": split},
              open(args.out, "w"), indent=1)
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
