"""Give the DOI-only papers enough metadata to be curated at all.

157 records in the curatable pool came from OpenCitations, which returns
citation edges and nothing else. They carry a bare DOI: no title, no venue, no
author, no abstract. Until they are enriched they cannot be judged, and quietly
dropping them would lose the works Semantic Scholar's 1,000-result cap hid --
MLIR, Reconfiguring the Imaging Pipeline, STELLA, ProxImaL, PolyMage, YASK.

Two keyless routes, used together because each covers the other's gaps:

  api.crossref.org   title, venue, year, type, authors with their RAW
                     affiliation strings, publisher, reference count, and a
                     JATS abstract for maybe half of them
  api.openalex.org   cited_by_count (which the tier split needs), concepts,
                     an abstract for most of the rest, and an open-access PDF
                     link when there is one

Crossref is the bibliographic ground truth. OpenAlex is taken only for the
fields Crossref does not carry: its INSTITUTION labels are about 12% wrong and
confidently so -- it has mapped MIT CSAIL to Vassar College and ARM Ltd. to the
American Rock Mechanics Association -- so affiliations come from Crossref's raw
strings and OpenAlex is never consulted for them.

Measured over all 157: every one resolved to a title, 102 to an abstract, and
73 needed OpenAlex for a field Crossref did not carry, so neither source alone
would have done. The 55 without abstracts are 52 book chapters plus three
others; Springer does not deposit chapter abstracts. That gap is benign -- the
most-cited record lacking an abstract has 25 citations and only three have ten
or more -- so it sits in the tail where rules will judge them anyway.

Both honour a polite pool keyed on a contact address; pass one.

    python3 curate/enrich_papers.py --mailto you@example.edu \
        --in data/pools/doi_only_papers.json \
        --out data/pools/doi_enriched_state.json
"""
import argparse, html, json, os, re, sys, time, urllib.error, urllib.parse, urllib.request

sys.stdout.reconfigure(line_buffering=True)

CROSSREF = "https://api.crossref.org/works/{doi}"
OPENALEX = "https://api.openalex.org/works/doi:{doi}"
TAG = re.compile(r"<[^>]+>")


def get(url, mailto, timeout=25):
    ua = f"halide-world-index/0.1 (https://github.com/samanamarasinghe/Halide-world; mailto:{mailto})"
    req = urllib.request.Request(url, headers={"User-Agent": ua})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())


def clean_abstract(text):
    """Crossref abstracts are JATS XML. Strip the tags, keep the prose."""
    if not text:
        return None
    return html.unescape(TAG.sub(" ", text)).strip() or None


def from_inverted_index(idx):
    """OpenAlex stores abstracts as {word: [positions]}. Put them back in order."""
    if not idx:
        return None
    pos = [(p, w) for w, ps in idx.items() for p in ps]
    return " ".join(w for _, w in sorted(pos)) or None


def crossref(doi, mailto):
    try:
        m = get(CROSSREF.format(doi=urllib.parse.quote(doi)), mailto)["message"]
    except urllib.error.HTTPError as e:
        return {"crossref_error": f"http {e.code}"}
    except Exception as e:
        return {"crossref_error": str(e)[:120]}
    authors = []
    for a in m.get("author") or []:
        name = " ".join(x for x in (a.get("given"), a.get("family")) if x) or a.get("name")
        # The raw affiliation string, never a normalised institution id.
        affs = [x.get("name") for x in (a.get("affiliation") or []) if x.get("name")]
        authors.append({"name": name, "affiliations": affs} if affs else {"name": name})
    issued = (m.get("issued", {}).get("date-parts") or [[None]])[0]
    return {
        "title": (m.get("title") or [None])[0],
        "venue": (m.get("container-title") or [None])[0],
        "year": issued[0] if issued else None,
        "type": m.get("type"),
        "publisher": m.get("publisher"),
        "authors": authors,
        "abstract": clean_abstract(m.get("abstract")),
        "reference_count": m.get("reference-count"),
        "subjects": m.get("subject") or [],
    }


def openalex(doi, mailto):
    try:
        d = get(OPENALEX.format(doi=urllib.parse.quote(doi)) + f"?mailto={mailto}", mailto)
    except urllib.error.HTTPError as e:
        return {"openalex_error": f"http {e.code}"}
    except Exception as e:
        return {"openalex_error": str(e)[:120]}
    loc = d.get("primary_location") or {}
    oa = d.get("best_oa_location") or {}
    return {
        "cited_by_count": d.get("cited_by_count"),
        "abstract": from_inverted_index(d.get("abstract_inverted_index")),
        "concepts": [c.get("display_name") for c in (d.get("concepts") or [])[:6]],
        "venue": (loc.get("source") or {}).get("display_name"),
        "year": d.get("publication_year"),
        "title": d.get("title"),
        "pdf_url": oa.get("pdf_url"),
    }


def merge(doi, cr, oa):
    """Crossref wins on bibliography; OpenAlex fills only what it does not have."""
    rec = {"doi": doi, "source": []}
    if "crossref_error" not in cr:
        rec.update({k: v for k, v in cr.items() if v not in (None, [], "")})
        rec["source"].append("crossref")
    else:
        rec["crossref_error"] = cr["crossref_error"]
    if "openalex_error" not in oa:
        for k in ("cited_by_count", "concepts", "pdf_url"):
            if oa.get(k) not in (None, [], ""):
                rec[k] = oa[k]
        for k in ("title", "venue", "year", "abstract"):
            if not rec.get(k) and oa.get(k):
                rec[k] = oa[k]
                rec.setdefault("filled_from_openalex", []).append(k)
        rec["source"].append("openalex")
    else:
        rec["openalex_error"] = oa["openalex_error"]
    # What curation actually cares about: is there any text to judge from?
    rec["has_text"] = bool(rec.get("abstract"))
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src", default="data/pools/doi_only_papers.json")
    ap.add_argument("--out", default="data/pools/doi_enriched_state.json")
    ap.add_argument("--mailto", required=True, help="contact address for the polite pools")
    ap.add_argument("--sleep", type=float, default=0.1)
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()

    dois = json.load(open(args.src))["dois"]
    if args.limit:
        dois = dois[:args.limit]
    state = json.load(open(args.out)) if os.path.exists(args.out) else {}
    todo = [d for d in dois if d not in state]
    print(f"{len(dois)} DOIs, {len(todo)} to fetch")

    t0 = time.time()
    for i, doi in enumerate(todo, 1):
        state[doi] = merge(doi, crossref(doi, args.mailto), openalex(doi, args.mailto))
        if i % 25 == 0 or i == len(todo):
            json.dump(state, open(args.out, "w"), indent=1)
            print(f"  {i}/{len(todo)}  {time.time()-t0:.0f}s")
        time.sleep(args.sleep)

    json.dump(state, open(args.out, "w"), indent=1)
    titled = sum(1 for v in state.values() if v.get("title"))
    texted = sum(1 for v in state.values() if v.get("has_text"))
    failed = sum(1 for v in state.values() if "crossref_error" in v and "openalex_error" in v)
    print(f"wrote {args.out}: {len(state)} records, {titled} with a title, "
          f"{texted} with an abstract, {failed} resolved by neither source")


if __name__ == "__main__":
    main()
