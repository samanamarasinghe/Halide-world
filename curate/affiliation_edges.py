"""Attach institutions to authorship EDGES — where they were when that happened.

This is the join his original ask needs. The pieces existed separately: the
authorship edges, the raw Crossref strings, and the string -> institution map.
None of them alone answers "where was this person when they wrote that paper",
because affiliation belongs to the EDGE, not the person. Someone at Stanford in
2013 and MIT in 2019 has two true answers and the index must carry both, dated.

Matching is by SURNAME within one paper's author list. That is deliberately a
small scope: `Chen` is hopeless across 5,688 authors and unambiguous among the
six names on one paper. Where a surname appears twice in the same author list
the edge is SKIPPED rather than guessed (383 of them), and the count is
reported -- an affiliation attached to the wrong coauthor is invisible once
written.

Person ids are the POST-DEDUPE canonical ids from `curate/author_dedupe.py`, so
an author whose S2 record was split does not appear as two people with half a
career each.

Measured 2026-08-19: 6,775 author slots -> 4,242 edges carrying an institution,
2,817 people with a dated institution, 299 of them at more than one institution
over time. The losses are all named in `counts` and none is silent: 1,633 slots
matched a Crossref author who has no affiliation deposited, 535 papers have no
Crossref record at all (arXiv and the Springer/Elsevier gap), 360 affiliation
strings did not normalise, 157 surnames did not match.

Spot-checked against careers that are publicly known: Ragan-Kelley MIT /
Stanford / Berkeley / Google, Kamil MIT -> Adobe, Tzu-Mao Li MIT -> Berkeley ->
UCSD. Those three are also how the normalisation leaks were found -- a person
appearing to "move" between two spellings of one university is the visible
symptom of an under-merged institution name.

    python3 curate/affiliation_edges.py --out data/pools/affiliation_edges.json
"""
import argparse, collections, json, re, sys

sys.stdout.reconfigure(line_buffering=True)


def surname(n):
    parts = [x for x in re.sub(r"[^A-Za-z \-']", " ", n or "").split() if len(x) > 1]
    return parts[-1].lower() if parts else ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--papers", default="data/pools/lane_a.json")
    ap.add_argument("--doi-map", default="data/pools/s2_doi_map.json")
    ap.add_argument("--affiliations", default="data/pools/affiliations_state.json")
    ap.add_argument("--normalized", default="data/pools/affiliations_normalized.json")
    ap.add_argument("--dedupe", default="data/pools/author_dedupe.json")
    ap.add_argument("--out", default="data/pools/affiliation_edges.json")
    args = ap.parse_args()

    works = json.load(open(args.papers))["works"]
    sid2doi = {s: v["doi"] for s, v in json.load(open(args.doi_map)).items()
               if v.get("doi")}
    aff = json.load(open(args.affiliations))
    norm = json.load(open(args.normalized))["map"]

    # post-dedupe identity: every merged id points at its canonical
    canon = {}
    for m in json.load(open(args.dedupe))["merged"]:
        for i in m["ids"]:
            canon[i] = m["canonical_id"]

    edges = []
    stats = collections.Counter()
    for sid, w in works.items():
        rec = aff.get(sid2doi.get(sid, ""))
        year = w.get("year")
        authors = w.get("authors") or []
        if not rec or rec.get("error"):
            stats["paper_no_crossref"] += 1
            continue
        cross = rec.get("authors") or []
        by_sn = collections.defaultdict(list)
        for c in cross:
            by_sn[surname(c.get("name"))].append(c)

        for a in authors:
            aid = a.get("s2_author_id")
            if not aid:
                continue
            stats["author_slots"] += 1
            cands = by_sn.get(surname(a.get("name"))) or []
            if not cands:
                stats["no_surname_match"] += 1
                continue
            if len(cands) > 1:
                # two people share a surname on one paper -- skip rather than
                # attach an affiliation to the wrong one
                stats["ambiguous_surname"] += 1
                continue
            raws = cands[0].get("affiliations") or []
            if not raws:
                stats["matched_but_no_affiliation"] += 1
                continue
            insts = []
            for r in raws:
                for i in (norm.get(r.strip()) or []):
                    if i not in insts:
                        insts.append(i)
            if not insts:
                stats["affiliation_unresolved"] += 1
                continue
            edges.append({"person_id": canon.get(aid, aid),
                          "name": a.get("name"), "paper": sid, "year": year,
                          "institutions": insts, "raw": raws})
            stats["edges"] += 1

    # per-person timeline
    people = collections.defaultdict(lambda: collections.defaultdict(list))
    names = {}
    for e in edges:
        names[e["person_id"]] = e["name"]
        for i in e["institutions"]:
            if e["year"]:
                people[e["person_id"]][i].append(e["year"])

    timelines = {}
    movers = 0
    for pid, insts in people.items():
        entry = {"name": names[pid],
                 "institutions": {i: {"first": min(ys), "last": max(ys),
                                      "n_papers": len(ys)}
                                  for i, ys in sorted(insts.items())}}
        if len(entry["institutions"]) > 1:
            movers += 1
        timelines[pid] = entry

    print(f"author slots seen        : {stats['author_slots']}")
    print(f"  EDGES WITH AN INSTITUTION: {stats['edges']}")
    print(f"  matched, none deposited : {stats['matched_but_no_affiliation']}")
    print(f"  no surname match        : {stats['no_surname_match']}")
    print(f"  ambiguous surname, skipped: {stats['ambiguous_surname']}")
    print(f"  affiliation unresolved  : {stats['affiliation_unresolved']}")
    print(f"papers with no Crossref record: {stats['paper_no_crossref']}")
    print(f"\npeople with at least one dated institution: {len(timelines)}")
    print(f"people at MORE THAN ONE institution over time: {movers}")

    json.dump({"schema_version": 1,
               "note": ("Authorship edges carrying the institution the author "
                        "was at FOR THAT PAPER. Surname-matched within a single "
                        "paper's author list; a surname appearing twice in one "
                        "list is skipped, not guessed. Person ids are "
                        "post-dedupe canonical ids."),
               "counts": dict(stats), "n_edges": len(edges),
               "n_people": len(timelines), "n_movers": movers,
               "timelines": timelines, "edges": edges},
              open(args.out, "w"), indent=1)
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
