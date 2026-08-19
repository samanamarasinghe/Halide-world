"""Resolve every S2 paper id to a DOI, so the affiliation lane has a key.

`lane_a.json` carries no DOI at all -- only title, venue, year and authors. The
affiliation route needs one, because raw affiliation strings come from Crossref
and Crossref is keyed on DOI. Until now that map lived in
`artifacts_state.json`, which is gitignored and exists on exactly one disk;
that is the recurring trap, and shipping this script ends it for this lane --
the map is now regenerable by anyone in ~18 minutes with no key.

The route is the keyless Semantic Scholar frontend endpoint already documented
in the project history:

    https://www.semanticscholar.org/api/1/paper/<s2_id>
    with a browser User-Agent AND Referer: https://www.semanticscholar.org/paper/<s2_id>

IT HAS CHANGED SHAPE since the harvest. The payload is now wrapped:

    {"responseType": "PAPER_DETAIL", "paper": {...}}

where it used to return the paper at the top level. Reading `doiInfo` from the
top level now silently yields None for every paper -- a failure that looks
exactly like "this paper has no DOI". The history file warned this endpoint is
undocumented and unstable; this is that warning coming true, so the parse below
accepts BOTH shapes and the run reports how many ids resolved, which is the
number that exposes a shape change next time.

The documented Graph API is not an alternative: keyless it now fails ~19 of 20
requests. 423 DOIs already sit in `data/pools/artifacts.json` and are reused
rather than re-fetched.

Measured run, 2026-08-19: 1,482 of 1,840 works carry a DOI (1,020 newly
resolved, 357 genuinely have none, 0 errors) at 0.76 s/paper.

    python3 curate/resolve_dois.py --out data/pools/s2_doi_map.json
"""
import argparse, json, os, sys, time, urllib.error, urllib.request

sys.stdout.reconfigure(line_buffering=True)

BROWSER = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
           "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def fetch(sid, timeout=30):
    req = urllib.request.Request(
        f"https://www.semanticscholar.org/api/1/paper/{sid}",
        headers={"User-Agent": BROWSER,
                 "Referer": f"https://www.semanticscholar.org/paper/{sid}"})
    payload = json.load(urllib.request.urlopen(req, timeout=timeout))
    # accept both the current envelope and the pre-2026 top-level shape
    paper = payload.get("paper") or payload
    doi = (paper.get("doiInfo") or {}).get("doi")
    venue = paper.get("venue")
    if isinstance(venue, dict):
        venue = venue.get("text")
    return {"doi": doi, "corpus_id": paper.get("corpusId"),
            "venue": venue, "year": paper.get("year")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", default="data/pools/lane_a.json")
    ap.add_argument("--artifacts", default="data/pools/artifacts.json")
    ap.add_argument("--out", default="data/pools/s2_doi_map.json")
    ap.add_argument("--sleep", type=float, default=0.6)
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()

    works = json.load(open(args.pool))["works"]
    state = json.load(open(args.out)) if os.path.exists(args.out) else {}

    if os.path.exists(args.artifacts):
        seeded = 0
        for p in json.load(open(args.artifacts))["papers"]:
            if p.get("doi") and p.get("s2_id") and p["s2_id"] not in state:
                state[p["s2_id"]] = {"doi": p["doi"], "source": "artifacts.json"}
                seeded += 1
        print(f"seeded {seeded} DOIs already in the repo")

    todo = [s for s in works if s not in state]
    if args.limit:
        todo = todo[:args.limit]
    print(f"{len(works)} works, {len(todo)} to resolve")

    t0, got, none_, err = time.time(), 0, 0, 0
    for i, sid in enumerate(todo, 1):
        try:
            rec = fetch(sid)
            rec["source"] = "s2_frontend"
            state[sid] = rec
            got += bool(rec["doi"])
            none_ += not rec["doi"]
        except urllib.error.HTTPError as e:
            state[sid] = {"error": f"http {e.code}"}
            err += 1
        except Exception as e:
            state[sid] = {"error": e.__class__.__name__}
            err += 1
        if i % 25 == 0:
            json.dump(state, open(args.out, "w"), indent=1)
            print(f"  {i}/{len(todo)}  {time.time()-t0:.0f}s  "
                  f"doi {got}, no-doi {none_}, err {err}")
        time.sleep(args.sleep)
    json.dump(state, open(args.out, "w"), indent=1)

    have = sum(1 for v in state.values() if v.get("doi"))
    print(f"\nwrote {args.out}: {have} of {len(works)} works now carry a DOI "
          f"({got} newly resolved, {none_} genuinely have none, {err} errors)")
    if todo and got == 0:
        print("  WARNING: nothing resolved -- check the payload shape before "
              "trusting this as 'no DOI'")


if __name__ == "__main__":
    main()
