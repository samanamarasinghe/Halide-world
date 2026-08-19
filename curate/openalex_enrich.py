"""Recover ABSTRACTS from OpenAlex for the papers the judged pass cannot read.

590 of the 1,053 escalating papers have no full text. The obvious response was
to fetch their PDFs; measured, that route returns roughly 10%, because ACM and
IEEE advertise an open-access location and then refuse the request (see
`curate/fetch_missing_fulltext.py`, which states that failure honestly).

The abstract route is far better, and it was the thing worth measuring:

    542 of the 590 carry a DOI
    408 of those 542 yield an abstract   (75%)
    125 also expose an OA pdf_url

WHAT IT DOES TO THE QUEUE, which is the number that matters:

    evidence tier      before   after
      ok                  130     287
      thin                176     170
      poor                284     133

133 papers still have nothing a judge can read. The other 151 moved out of
`poor` because the paper's own summary of itself is now available. That is the
difference between a verdict and a shrug, and it cost under three minutes.

THE KEY IS READ FROM THE ENVIRONMENT and is never stored here or in the repo:

    export OPENALEX_API_KEY=...
    python3 curate/openalex_enrich.py --out data/pools/openalex_abstracts.json

Without a key OpenAlex still answers, but it meters by daily budget and a single
enrichment run exhausts the free allowance -- `title.search` then returns 429
"Insufficient budget" while direct `/works/doi:` lookups still succeed, which
makes the failure look like a missing record rather than a spent quota.

STANDING RULE, UNCHANGED: OpenAlex may supply abstracts and open-access
locations. It is NEVER consulted for affiliations -- roughly 12% of its
institution labels are unsupported by the paper's own text, and confidently
wrong (ARM Ltd -> American Rock Mechanics Association, MIT CSAIL -> Vassar
College). The raw Crossref string stays ground truth for that.
"""
import argparse, collections, json, os, sys, time
import urllib.error, urllib.parse, urllib.request

sys.stdout.reconfigure(line_buffering=True)

UA = {"User-Agent": "halide-world/1.0 (mailto:saman@lcs.mit.edu)"}


def reassemble(inverted):
    """OpenAlex ships abstracts as {word: [positions]}. Rebuild by position."""
    if not inverted:
        return None
    slots = {}
    for word, positions in inverted.items():
        for p in positions:
            slots[p] = word
    if not slots:
        return None
    return " ".join(slots[i] for i in sorted(slots))


def fetch(doi, key, mailto):
    url = f"https://api.openalex.org/works/doi:{urllib.parse.quote(doi)}"
    sep = "&" if "?" in url else "?"
    q = f"{url}{sep}mailto={mailto}" + (f"&api_key={key}" if key else "")
    return json.load(urllib.request.urlopen(
        urllib.request.Request(q, headers=UA), timeout=30))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prepass", default="data/pools/prepass.json")
    ap.add_argument("--doi-map", default="data/pools/s2_doi_map.json")
    ap.add_argument("--out", default="data/pools/openalex_abstracts.json")
    ap.add_argument("--mailto", default="saman@lcs.mit.edu")
    ap.add_argument("--sleep", type=float, default=0.15)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--all-escalating", action="store_true",
                    help="not just the no-full-text ones")
    args = ap.parse_args()

    key = os.environ.get("OPENALEX_API_KEY")
    print("OpenAlex key: " + ("present" if key else
                              "ABSENT -- expect the daily budget to run out"))

    pre = json.load(open(args.prepass))
    rows = [r for r in pre["escalating"]
            if args.all_escalating or r.get("prepass") == "no full text"]
    dm = {s: v["doi"] for s, v in json.load(open(args.doi_map)).items()
          if v.get("doi")}

    targets = []
    for r in rows:
        pid = r["id"]
        doi = pid[3:] if pid.startswith("oc:") else dm.get(pid)
        if doi:
            targets.append((pid, doi))
    print(f"{len(targets)} of {len(rows)} targets carry a DOI")

    state = json.load(open(args.out)) if os.path.exists(args.out) else {}
    todo = [t for t in targets if t[0] not in state]
    if args.limit:
        todo = todo[:args.limit]
    print(f"{len(todo)} to fetch")

    stats = collections.Counter()
    t0 = time.time()
    for i, (pid, doi) in enumerate(todo, 1):
        try:
            j = fetch(doi, key, args.mailto)
        except urllib.error.HTTPError as e:
            state[pid] = {"error": f"http {e.code}", "doi": doi}
            stats[f"http_{e.code}"] += 1
            if e.code == 429:
                print("  429 -- budget exhausted; a key removes this")
                break
            continue
        except Exception as e:
            state[pid] = {"error": e.__class__.__name__, "doi": doi}
            stats["error"] += 1
            continue

        abstract = reassemble(j.get("abstract_inverted_index"))
        loc = j.get("best_oa_location") or {}
        state[pid] = {"doi": doi, "title": j.get("title"),
                      "abstract": abstract,
                      "pdf_url": loc.get("pdf_url"),
                      "is_oa": bool(j.get("open_access", {}).get("is_oa")),
                      "cited_by_count": j.get("cited_by_count")}
        stats["abstract" if abstract else "no_abstract"] += 1
        if loc.get("pdf_url"):
            stats["with_pdf_url"] += 1
        if i % 100 == 0:
            json.dump(state, open(args.out, "w"), indent=1)
            print(f"  {i}/{len(todo)}  {time.time()-t0:.0f}s  "
                  f"abstracts {stats['abstract']}")
        time.sleep(args.sleep)
    json.dump(state, open(args.out, "w"), indent=1)

    got = sum(1 for v in state.values() if v.get("abstract"))
    print(f"\nwrote {args.out}: {len(state)} records, {got} with an abstract "
          f"({100*got//max(len(state),1)}%)")
    for k, v in stats.most_common():
        print(f"  {k:16s} {v}")


if __name__ == "__main__":
    main()
