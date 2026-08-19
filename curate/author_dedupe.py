"""Author-layer dedupe — collapse the S2 author ids that are the same human.

S2 over-splits authors and never conflates them: 5,214 distinct names carry
5,688 ids, 362 names hold more than one id, and NO id holds more than one name
spelling. So the id is a safe atom and the only question is whether two ids
under the same name are one person.

His ruling of 2026-08-19: resolve with a SECOND SIGNAL, no hand review.

EVERY candidate signal was measured against a control of random pairs of ids
belonging to DIFFERENT names -- pairs we know must not merge. A signal is worth
having only if it fires far more often on the target set than on the control.

  paper        the two ids appear on the same paper. HIS RULING: this means one
               human whose entry the source duplicated, not two people
  affiliation  their raw affiliation strings share an institution token, taken
               from the paper's own Crossref record and matched on surname
               within that one author list. 67% target vs 2% control -- by far
               the strongest signal here, and the one that settled Christophe
               Dubach, whose two ids (1 and 17 papers) share no coauthor at all
  coauthor     their coauthor NAME sets intersect. Keyed on name, never on id --
               an id key is degraded by the very splitting it is meant to fix,
               because the coauthor is split too (name-keyed links 251 groups
               where id-keyed links 218)
  2-hop        one id's coauthors, expanded one hop through the global coauthor
               graph, reach the other's. 17% target vs 4% control: real but
               thin. It earned its place on Andrew Adams (3 ids, all his) and
               Frédo Durand (2)

MEASURED AND REJECTED as non-discriminative: shared venue (9% target / 5%
control) and shared field of study (98% / 97% -- almost every record here is
"Computer Science").

A group merges only if EVERY pair inside it is linked. Requiring a clique is
the whole point: linking A-B and B-C does not make A and C the same person, and
merging is transitive, which is how `unknown` once chained four different
halide/Halide contributors into one node.

What cannot be settled is LEFT SPLIT and tagged, never guessed. Over-merging is
worse than under-merging: a split person is visible and fixable, a falsely
merged one is not.

Result with affiliations folded in: 1 merged on a shared paper, 196 on a shared
coauthor, 31 on a shared affiliation, 17 via 2-hop, 117 left split, 297 author
ids collapsed. THE REMAINING 117 ARE MOSTLY A COVERAGE PROBLEM, NOT A SIGNAL
ONE -- 92 of them have at least one pair where one id carries no affiliation at
all, because Springer and Elsevier deposit none in Crossref and arXiv DOIs are
not in Crossref.

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


def load_affiliations(aff_path, doi_path, works):
    """S2 author id -> normalised affiliation tokens, via the paper's Crossref
    record. Matched on SURNAME within a single paper's author list, which is a
    small enough scope for a surname to be unambiguous."""
    import os, re
    if not (os.path.exists(aff_path) and os.path.exists(doi_path)):
        return {}
    aff = json.load(open(aff_path))
    sid2doi = {s: v["doi"] for s, v in json.load(open(doi_path)).items() if v.get("doi")}
    stop = {"university", "univ", "institute", "of", "the", "department", "dept",
            "school", "college", "and", "for", "laboratory", "lab", "center",
            "centre", "research", "inc", "ltd", "corp", "gmbh", "technology",
            "science", "sciences", "engineering", "computer", "usa", "china",
            "germany", "france"}

    def norm(s):
        return {w for w in re.sub(r"[^a-z0-9 ]", " ", s.lower()).split()
                if len(w) > 2 and w not in stop}

    def surname(n):
        parts = [x for x in re.sub(r"[^A-Za-z \-]", " ", n).split() if len(x) > 1]
        return parts[-1].lower() if parts else ""

    out = collections.defaultdict(set)
    for sid, w in works.items():
        rec = aff.get(sid2doi.get(sid, ""))
        if not rec or rec.get("error"):
            continue
        cross = {surname(a["name"]): a for a in rec.get("authors", []) if a.get("name")}
        for a in (w.get("authors") or []):
            i, c = a.get("s2_author_id"), cross.get(surname(a.get("name") or ""))
            if i and c and c.get("affiliations"):
                for raw in c["affiliations"]:
                    out[i] |= norm(raw)
    return out


def evidence(a, b, co, papers, nbr, aff=None):
    if papers[a] & papers[b]:
        return "paper"
    if co[a] & co[b]:
        return "coauthor"
    if aff and aff.get(a) and aff.get(b) and aff[a] & aff[b]:
        return "affiliation"
    expanded = set(co[a])
    for x in co[a]:
        expanded |= nbr[x]
    if expanded & co[b]:
        return "2-hop"
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--papers", default="data/pools/lane_a.json")
    ap.add_argument("--affiliations", default="data/pools/affiliations_state.json")
    ap.add_argument("--doi-map", default="data/pools/s2_doi_map.json")
    ap.add_argument("--out", default="data/pools/author_dedupe.json")
    args = ap.parse_args()

    works = json.load(open(args.papers))["works"]
    co, papers, name_ids, nbr = build(works)
    aff = load_affiliations(args.affiliations, args.doi_map, works)
    print(f"{len(aff)} author ids carry a raw affiliation")
    multi = {n: sorted(ids) for n, ids in name_ids.items() if len(ids) > 1}
    print(f"{len(name_ids)} names, {sum(len(v) for v in name_ids.values())} ids, "
          f"{len(multi)} names with more than one id")

    merged, split = [], []
    counts = collections.Counter()
    for n, ids in sorted(multi.items()):
        pairs = list(itertools.combinations(ids, 2))
        ev = {p: evidence(p[0], p[1], co, papers, nbr, aff) for p in pairs}
        if all(ev.values()):
            # the WEAKEST link in the group names the group, so a group labelled
            # `2-hop` is one held together by the thinnest evidence in the set.
            # The order is the measured discrimination, not intuition.
            vals = set(ev.values())
            strongest = ("2-hop" if "2-hop" in vals else
                         "affiliation" if "affiliation" in vals else
                         "coauthor" if "coauthor" in vals else "paper")
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
                          "affiliation_known": {i: bool(aff.get(i)) for i in ids},
                          "reason": "no evidence links every pair; left split "
                                    "rather than guessed"})
            counts["left_split"] += 1

    ids_removed = sum(len(m["ids"]) - 1 for m in merged)
    print(f"\n  merged on a shared paper     : {counts['merged_paper']}")
    print(f"  merged on a shared coauthor  : {counts['merged_coauthor']}")
    print(f"  merged on a shared affiliation: {counts['merged_affiliation']}")
    print(f"  merged via the 2-hop signal  : {counts['merged_2-hop']}")
    print(f"  LEFT SPLIT, tagged           : {counts['left_split']}")
    print(f"  author ids collapsed away    : {ids_removed}")

    json.dump({"schema_version": 1,
               "note": ("Author-layer dedupe. A group merges only when EVERY "
                        "pair in it is linked. Unsettled groups are LEFT SPLIT "
                        "and tagged, never guessed. `affiliation_known` says "
                        "whether the residual is a signal problem or a coverage "
                        "one."),
               "signal_discrimination": {
                   "affiliation": "67% target vs 2% control",
                   "two_hop": "17% target vs 4% control",
                   "shared_venue": "9% vs 5% -- REJECTED",
                   "shared_field": "98% vs 97% -- REJECTED, non-discriminative"},
               "n_merged": len(merged), "n_left_split": len(split),
               "ids_collapsed": ids_removed,
               "merged": merged, "left_split": split},
              open(args.out, "w"), indent=1)
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
