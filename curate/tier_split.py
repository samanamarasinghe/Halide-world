"""Tier split — score every curatable record by STAKES and report the shape.

Saman's ruling of 2026-08-18: tier first, rules over the tail, judged pass over
the head. And his standing rule: do NOT set a cutoff before measuring the space.
So this script deliberately does NOT choose a cut. It scores, reports the
distribution, and prints what several candidate cuts would cost.

STAKES, not evidence strength. Splitting on evidence would send all the
evidence-poor records to the tail, which is exactly where rules cannot judge
them (the ISCA'16 case: a title that reads like Halide-to-Hardware and is the
Stanford Spatial line instead). Stakes asks a different question: how much does
it cost to get THIS record's role wrong?

Two things therefore come out of this script, not one:
  tier      head | tail          -- how much a wrong answer costs
  evidence  ok | thin | poor     -- whether a rule could answer at all
and `escalate = head OR poor`, which is the set the judged pass must see.

    python3 curate/tier_split.py --out data/pools/tiers.json
"""
import argparse, json, os, sys, collections

sys.stdout.reconfigure(line_buffering=True)

# --- paper stakes ----------------------------------------------------------
# Citations are the loudest signal but must not dominate: FlashAttention has
# 5,034 citations and importance 1 WITHIN the Halide world. Citations say "many
# people will look at this record", which is stakes; they do not say "this is
# central to Halide", which is importance. Anchor breadth and the influential
# flag are the Halide-specific counterweights.
def paper_stakes(w, enriched, artifact_papers):
    cites = w.get("num_cited_by") or enriched.get("cited_by_count") or 0
    s = 0.0
    if cites >= 1000: s += 4
    elif cites >= 250: s += 3
    elif cites >= 50:  s += 2
    elif cites >= 10:  s += 1
    s += 2 * len(w.get("key_on") or [])          # influential on an anchor
    s += min(len(w.get("cites_anchors") or []), 4) * 0.5
    if w.get("s2_id") in artifact_papers or w.get("doi") in artifact_papers:
        s += 2                                    # an artifact makes it checkable AND visible
    if "methodology" in (w.get("intents") or []):
        s += 1                                    # the free "uses" signal
    return s


def paper_evidence(w, enriched):
    n = w.get("n_contexts") or 0
    has_abstract = bool(enriched.get("abstract"))
    if n >= 2 or (n == 1 and has_abstract):
        return "ok"
    if n == 1 or has_abstract:
        return "thin"
    return "poor"


# --- repo stakes -----------------------------------------------------------
# Stars are the paper-citation analogue and carry the same caveat:
# scanner-research/scanner has 624 stars and importance 2. n_matches is a real
# signal ONLY when the evidence is not Halide's own vendored tree -- there it
# counts Halide's files, not the repo's use of them.
def repo_stakes(r):
    m = r.get("meta") or {}
    stars = m.get("stargazers_count") or 0
    s = 0.0
    if stars >= 5000: s += 4
    elif stars >= 500: s += 3
    elif stars >= 50:  s += 2
    elif stars >= 5:   s += 1
    vendored = "evidence_is_halides_own_tree" in r["flags"]
    if not vendored:
        n = r.get("n_matches") or 0
        if n >= 100: s += 2
        elif n >= 20: s += 1
    if r.get("role_source") == "fork_diff":
        s += 3            # already known to extend Halide: the costly ones to misfile
    return s


def repo_evidence(r, meta_all):
    """The README lives in repo_meta_state.json, NOT in the cleanup record --
    cleanup_repos copies only a fixed field list into `meta`. Reading it from
    the record alone reported 0 repos with usable evidence while 549 READMEs
    sat on disk."""
    m = r.get("meta") or {}
    raw = meta_all.get(r["repo"], {}) or {}
    has_desc = bool(m.get("description") or raw.get("description"))
    has_readme = bool(raw.get("readme"))
    if m.get("unindexed") and not has_readme:
        return "poor"
    if has_desc and has_readme:
        return "ok"
    if has_desc or has_readme:
        return "thin"
    return "poor"


def histogram(scores, width=60):
    buckets = collections.Counter(int(s) for s in scores)
    top = max(buckets.values()) if buckets else 1
    for k in sorted(buckets):
        bar = "#" * max(1, int(width * buckets[k] / top))
        print(f"  {k:>4} | {buckets[k]:>5}  {bar}")


def report(kind, rows):
    scores = [r["stakes"] for r in rows]
    scores.sort(reverse=True)
    print(f"\n=== {kind}: {len(rows)} records ===")
    histogram(scores)
    ev = collections.Counter(r["evidence"] for r in rows)
    print("  evidence: " + ", ".join(f"{k} {v}" for k, v in sorted(ev.items())))
    print(f"  {'cut':>6} {'head':>7} {'tail':>7} {'poor in tail':>13} {'judged pass':>12}")
    for cut in (2, 3, 4, 5, 6, 7, 8):
        head = [r for r in rows if r["stakes"] >= cut]
        tail = [r for r in rows if r["stakes"] < cut]
        poor = [r for r in tail if r["evidence"] == "poor"]
        # the judged pass sees the head plus every low-evidence record anywhere
        judged = len(head) + len(poor)
        print(f"  {cut:>6} {len(head):>7} {len(tail):>7} {len(poor):>13} {judged:>12}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--papers", default="data/pools/lane_a_compact.json")
    ap.add_argument("--enriched", default="data/pools/doi_enriched_state.json")
    ap.add_argument("--artifacts", default="data/pools/artifacts_attributed.json")
    ap.add_argument("--dups", default="data/pools/duplicates.json")
    ap.add_argument("--repos", default="data/pools/lane_b_curatable.json")
    ap.add_argument("--repometa", default="data/pools/repo_meta_state.json")
    ap.add_argument("--out", default="data/pools/tiers.json")
    args = ap.parse_args()

    enriched = json.load(open(args.enriched)) if os.path.exists(args.enriched) else {}
    dups = json.load(open(args.dups)) if os.path.exists(args.dups) else {}
    anchors = set(dups.get("anchors_inside_pool") or [])
    # A duplicate group is a list of ids for one work. The FIRST id is the
    # winner and the rest are losers -- the winner is pinned by position, which
    # is why the group order must never be re-sorted downstream. That is also
    # why this rebuild can disagree with an earlier one by a couple of records;
    # pinning the winner explicitly in duplicates.json is still owed.
    losers = set()
    for kind, groups in (dups.get("groups") or {}).items():
        for grp in groups:
            losers.update(grp[1:])

    art = json.load(open(args.artifacts)) if os.path.exists(args.artifacts) else {}
    artifact_papers = set()
    for rec in (art.get("papers") or art.get("records") or []):
        if rec.get("own_artifacts") or rec.get("is_own_artifact"):
            for k in ("s2_id", "doi", "paper_id"):
                if rec.get(k):
                    artifact_papers.add(rec[k])

    works = json.load(open(args.papers))["works"]
    paper_rows = []
    seen = set()
    for w in works:
        pid = w.get("s2_id") or w.get("doi")
        if pid in losers or pid in anchors or pid in seen:
            continue
        seen.add(pid)
        e = enriched.get(w.get("doi") or "", {}) or {}
        paper_rows.append({
            "id": pid, "kind": "paper", "title": (w.get("title") or "")[:120],
            "stakes": paper_stakes(w, e, artifact_papers),
            "evidence": paper_evidence(w, e),
            "cites": w.get("num_cited_by") or e.get("cited_by_count") or 0,
        })

    # The OpenCitations-only records are NOT in lane_a_compact -- they were
    # discovered by DOI alone and enriched separately. Leaving them out silently
    # loses 157 curatable papers, among them MLIR (524 cites) and Gharbi/Durand's
    # demosaicking paper (496). They are keyed `oc:<doi>` in the duplicate file.
    for doi, e in enriched.items():
        pid = "oc:" + doi
        if pid in losers or pid in anchors or pid in seen:
            continue
        seen.add(pid)
        w = {"doi": doi, "num_cited_by": e.get("cited_by_count") or 0,
             "cites_anchors": [], "key_on": [], "intents": [], "n_contexts": 0}
        paper_rows.append({
            "id": pid, "kind": "paper", "title": (e.get("title") or "")[:120],
            "stakes": paper_stakes(w, e, artifact_papers),
            "evidence": paper_evidence(w, e),
            "cites": e.get("cited_by_count") or 0,
        })

    repo_meta = json.load(open(args.repometa)) if os.path.exists(args.repometa) else {}
    repos = [r for r in json.load(open(args.repos))["repos"]
             if r["status"] == "curatable"]
    repo_rows = [{
        "id": r["repo"], "kind": "repo",
        "title": (r.get("meta", {}) or {}).get("description") or "",
        "stakes": repo_stakes(r), "evidence": repo_evidence(r, repo_meta),
        "stars": (r.get("meta", {}) or {}).get("stargazers_count") or 0,
    } for r in repos]

    report("PAPERS", paper_rows)
    report("REPOS", repo_rows)

    print("\n--- top 15 papers by stakes ---")
    for r in sorted(paper_rows, key=lambda x: -x["stakes"])[:15]:
        print(f"  {r['stakes']:>5.1f}  {r['cites']:>6}c  {r['evidence']:<5} {r['title'][:78]}")
    print("\n--- top 15 repos by stakes ---")
    for r in sorted(repo_rows, key=lambda x: -x["stakes"])[:15]:
        print(f"  {r['stakes']:>5.1f}  {r['stars']:>6}*  {r['evidence']:<5} {r['id'][:50]}")

    json.dump({"schema_version": 1,
               "note": ("Stakes scores only. NO CUT IS SET -- the cut is Saman's "
                        "ruling. `escalate` is head OR evidence=poor."),
               "n_papers": len(paper_rows), "n_repos": len(repo_rows),
               "papers": sorted(paper_rows, key=lambda x: -x["stakes"]),
               "repos": sorted(repo_rows, key=lambda x: -x["stakes"])},
              open(args.out, "w"), indent=1)
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
