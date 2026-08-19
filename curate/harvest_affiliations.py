"""Harvest RAW affiliation strings, so the index can say where someone was.

His original ask was per-person granularity: which papers each person wrote and
**where they were when that happened**. Affiliation is a property of the
authorship EDGE, not of the person -- someone at Stanford in 2013 and at MIT in
2019 has two true answers, and the index must carry both.

Ground truth is the affiliation string printed on the paper. Crossref carries
it, keyed on DOI, keyless. `curate/affiliations.py` already encodes the rule
that OpenAlex may only corroborate that string and never replace it (~12% of
its institution labels are unsupported by the paper's own text, and wrong
confidently: ARM Ltd. -> American Rock Mechanics Association, MIT CSAIL ->
Vassar College). This script does the fetching half and stops at the raw
string; normalisation stays where the aliases already live.

COVERAGE IS PUBLISHER-SHAPED, measured on a 30-DOI sample before running and
confirmed over the full set: ACM 3,688/3,699 author slots carry an affiliation,
IEEE 1,160/2,139, Springer 0/576, Elsevier 0/278. That is not a defect to fix --
Springer and Elsevier simply do not deposit affiliations in Crossref. The
corpus is favourably distributed anyway: ACM and IEEE together are 68% of the
1,482 resolved DOIs.

So a paper with no affiliation data is recorded as `no_affiliation_deposited`
with its registrant, NOT as a gap to retry. Retrying Elsevier forever is the
shape of a loop that never finishes. The 177 hard errors are all http 404 and
147 of them are arXiv DOIs, which Crossref does not hold at all -- also
structural, also not a retry.

Full run 2026-08-19: 1,631 papers, 7,449 authorship slots, 5,283 carrying a raw
affiliation (70%), ~10 minutes.

    python3 curate/harvest_affiliations.py --out data/pools/affiliations_state.json
"""
import argparse, collections, json, os, sys, time, urllib.error, urllib.parse, urllib.request

sys.stdout.reconfigure(line_buffering=True)

REGISTRANT = {"10.1145": "ACM", "10.1109": "IEEE", "10.1007": "Springer",
              "10.1016": "Elsevier", "10.1002": "Wiley", "10.48550": "arXiv",
              "10.1117": "SPIE", "10.3390": "MDPI", "10.1093": "OUP"}


def registrant(doi):
    return REGISTRANT.get(doi.split("/")[0], doi.split("/")[0])


def fetch(doi, mailto, timeout=25):
    url = "https://api.crossref.org/works/" + urllib.parse.quote(doi)
    req = urllib.request.Request(
        url, headers={"User-Agent": f"halide-world/1.0 (mailto:{mailto})"})
    msg = json.load(urllib.request.urlopen(req, timeout=timeout))["message"]
    authors = []
    for a in (msg.get("author") or []):
        name = " ".join(filter(None, [a.get("given"), a.get("family")])).strip()
        if not name:
            name = (a.get("name") or "").strip()
        affs = [x.get("name", "").strip()
                for x in (a.get("affiliation") or []) if x.get("name")]
        authors.append({"name": name, "orcid": a.get("ORCID"),
                        "affiliations": affs, "sequence": a.get("sequence")})
    year = None
    for k in ("published-print", "published-online", "issued"):
        parts = (msg.get(k) or {}).get("date-parts") or [[]]
        if parts[0]:
            year = parts[0][0]
            break
    return {"doi": doi, "year": year, "publisher": msg.get("publisher"),
            "registrant": registrant(doi), "authors": authors,
            "n_with_affiliation": sum(1 for a in authors if a["affiliations"])}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--doi-map", default="data/pools/s2_doi_map.json")
    ap.add_argument("--enriched", default="data/pools/doi_enriched_state.json",
                    help="the 157 OpenCitations-only papers, already Crossref-enriched")
    ap.add_argument("--out", default="data/pools/affiliations_state.json")
    ap.add_argument("--mailto", default="saman@lcs.mit.edu")
    ap.add_argument("--sleep", type=float, default=0.35)
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()

    dois = {}
    for sid, rec in json.load(open(args.doi_map)).items():
        if rec.get("doi"):
            dois[rec["doi"]] = sid
    print(f"{len(dois)} DOIs from the S2 map")

    state = json.load(open(args.out)) if os.path.exists(args.out) else {}

    # the 157 OpenCitations-only papers were already pulled from Crossref by
    # enrich_papers.py -- reuse rather than re-fetch
    if os.path.exists(args.enriched):
        reused = 0
        for doi, rec in json.load(open(args.enriched)).items():
            if doi in state:
                continue
            auth = [{"name": a.get("name"), "orcid": a.get("orcid"),
                     "affiliations": a.get("affiliations") or []}
                    for a in (rec.get("authors") or [])]
            if auth:
                state[doi] = {"doi": doi, "year": rec.get("year"),
                              "publisher": rec.get("publisher"),
                              "registrant": registrant(doi), "authors": auth,
                              "n_with_affiliation": sum(
                                  1 for a in auth if a["affiliations"]),
                              "source": "enrich_papers"}
                reused += 1
        print(f"reused {reused} already-enriched OpenCitations records")

    todo = [d for d in dois if d not in state]
    if args.limit:
        todo = todo[:args.limit]
    print(f"{len(todo)} to fetch")

    t0, ok, empty, err = time.time(), 0, 0, 0
    for i, doi in enumerate(todo, 1):
        try:
            rec = fetch(doi, args.mailto)
            rec["s2_id"] = dois[doi]
            if not rec["n_with_affiliation"]:
                rec["note"] = "no_affiliation_deposited"
                empty += 1
            else:
                ok += 1
            state[doi] = rec
        except urllib.error.HTTPError as e:
            state[doi] = {"doi": doi, "registrant": registrant(doi),
                          "error": f"http {e.code}"}
            err += 1
            if e.code == 429:
                time.sleep(5)
        except Exception as e:
            state[doi] = {"doi": doi, "registrant": registrant(doi),
                          "error": e.__class__.__name__}
            err += 1
        if i % 50 == 0:
            json.dump(state, open(args.out, "w"), indent=1)
            print(f"  {i}/{len(todo)}  {time.time()-t0:.0f}s  "
                  f"with-affil {ok}, none-deposited {empty}, err {err}")
        time.sleep(args.sleep)
    json.dump(state, open(args.out, "w"), indent=1)

    edges = sum(len(v.get("authors") or []) for v in state.values())
    filled = sum(1 for v in state.values() for a in (v.get("authors") or [])
                 if a.get("affiliations"))
    byreg = collections.Counter()
    byreg_ok = collections.Counter()
    for v in state.values():
        for a in (v.get("authors") or []):
            byreg[v.get("registrant")] += 1
            byreg_ok[v.get("registrant")] += bool(a.get("affiliations"))
    print(f"\nwrote {args.out}: {len(state)} papers, {edges} authorship slots, "
          f"{filled} carry a raw affiliation ({100*filled//max(edges,1)}%)")
    for r, n in byreg.most_common(8):
        print(f"   {str(r):10s} {byreg_ok[r]:5d}/{n:<5d}")


if __name__ == "__main__":
    main()
