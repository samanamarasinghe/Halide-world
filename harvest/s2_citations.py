#!/usr/bin/env python3
"""Harvest citing works for every Halide-world anchor, without an API key.

Semantic Scholar's documented Graph API requires a key and returns 429 to
unauthenticated callers. The web site's own frontend endpoint does not:

    https://www.semanticscholar.org/api/1/paper/<s2_id>/citations?offset=<n>

It returns strictly more than the Graph API would -- per-citation contexts
(the actual citing sentences), an intent label on each context
(background / methodology / result), and the isKey influential-citation flag.

This is an undocumented internal endpoint with no stability guarantee. When the
project's own API key arrives, port `fetch_citations` to the Graph API and keep
everything else; the record shape written here is deliberately close to it.

Usage:
    python3 harvest/s2_citations.py --out data/pools/lane_a.json

Writes two files: the full pool (with contexts) and a compact pool (contexts
summarised to intents plus a count), because the full pool is a few megabytes.
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter

BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
API = "https://www.semanticscholar.org/api/1/paper"

# Hard cap on results the endpoint will serve for one query. Only the PLDI 2013
# anchor exceeds it, so we make a second pass under a different sort order and
# union the two; OpenCitations and Scholar backfill whatever still falls short.
RESULT_CAP = 1000
PAGE = 10  # fixed server-side; pageSize is ignored

# Resolved once and pinned here. The endpoint does not accept DOIs, and the
# search endpoint returns 403, so ids were recovered by matching anchor titles
# inside other anchors' citing and reference lists.
#
# Two anchors have no Semantic Scholar record and are absent below: the 2014 MIT
# dissertation (no DOI, DSpace handle only) and the 2015 SIGGRAPH course notes.
# Both must come from the Google Scholar lane.
ANCHOR_S2_IDS = {
    "siggraph2012-decoupling": "3e06546182d5a36796a0f48e70151bf1d38e094d",
    "pldi2013-halide": "4d23db55e6671a82c95dacec33b2967a4b8b677d",
    "pldi2015-helium": "8d912672d78f71d6f6ef4db4c1655159827dc887",
    "ppopp2016-distributed": "886b7dcdc41055d2196c2d44db9490a87b1da55b",
    "siggraph2016-autoscheduler": "9b240a87b11d085641d6640f73cc3cc2d678e305",
    "cgo2017-reductions": "261178d4e8eaaf8c74d4a0fb263e9b4f94b09fe3",
    "cacm2018-halide": "93bb58cfdd34521c59e593d8f4332a75a18e3448",
    "siggraph2018-differentiable": "c1c8d15520d84ed6d9a701e18627ded4d8f1eb2a",
    "siggraph2019-treesearch": "f90a7bc396e205b204d5d6066a10162f84b128f9",
    "siggraphasia2019-translating": "8a52c0852c1a38c9f24a14704e1fb749b55ddbba",
    "oopsla2020-trs": "5a42db4c23c40acc46dc2e846fa4a4c22c44e3ff",
    "oopsla2021-gpu": "dcea274b58d1c767c2e25d776fe2af4b0181478f",
    "arxiv2022-semantics": "6d96a56047bc3ca1b9c36d59f53573b211726f56",
}


def text_of(field):
    """Titles and venues arrive as {"text": ..., "fragments": [...]}."""
    if isinstance(field, dict):
        return field.get("text", "")
    return field or ""


def normalize_title(title):
    return re.sub(r"[^a-z0-9 ]", "", re.sub(r"\s+", " ", title.lower())).strip()


def get_json(url, referer_id, tries=5):
    """GET with backoff. The endpoint needs a Referer naming the paper page."""
    headers = {
        "User-Agent": BROWSER_UA,
        "Accept": "application/json",
        "Referer": f"https://www.semanticscholar.org/paper/{referer_id}",
    }
    for attempt in range(tries):
        try:
            request = urllib.request.Request(url, headers=headers)
            return json.load(urllib.request.urlopen(request, timeout=50))
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 503):
                time.sleep(2 + 2 * attempt)
                continue
            raise
        except Exception:
            time.sleep(2)
    raise RuntimeError(f"gave up on {url}")


def fetch_citations(anchor_id, s2_id, verbose=True):
    """Every citing work for one anchor, keyed by Semantic Scholar id."""
    found = {}
    reported = None
    # Two sort orders return two different windows into the same list. For an
    # anchor under the cap the first pass is complete and the second is skipped.
    for sort in ("relevance", "pub-date"):
        base = f"{API}/{s2_id}/citations?sort={sort}"
        first = get_json(base, s2_id)
        reported = first["totalCitations"]
        for offset in range(0, min(reported, RESULT_CAP), PAGE):
            page = first if offset == 0 else get_json(f"{base}&offset={offset}", s2_id)
            if not page["citations"]:
                break
            for citation in page["citations"]:
                found[citation["id"]] = citation
        if reported <= RESULT_CAP:
            break
    if verbose:
        short = "" if len(found) == reported else f"  ({reported - len(found)} short of cap)"
        print(f"  {anchor_id:32s} reported {reported:5d}  harvested {len(found):5d}{short}")
    return found, reported


def to_record(citation):
    return {
        "s2_id": citation["id"],
        "title": text_of(citation.get("title")),
        "year": citation.get("year"),
        "venue": text_of(citation.get("venue")),
        "num_cited_by": citation.get("numCitedBy"),
        "fields": citation.get("fieldsOfStudy") or [],
        "authors": [
            {"name": a[0]["name"], "s2_author_id": (a[0].get("ids") or [None])[0]}
            for a in citation.get("authors", [])
            if a and isinstance(a[0], dict)
        ],
        "cites_anchors": {},
        "contexts": [],
    }


def harvest(anchors=ANCHOR_S2_IDS):
    works = {}
    per_anchor = {}
    for anchor_id, s2_id in sorted(anchors.items()):
        citations, reported = fetch_citations(anchor_id, s2_id)
        per_anchor[anchor_id] = {"reported": reported, "harvested": len(citations)}
        for s2_cite_id, citation in citations.items():
            work = works.setdefault(s2_cite_id, to_record(citation))
            work["cites_anchors"][anchor_id] = {"is_key": bool(citation.get("isKey"))}
            for context in citation.get("citationContexts") or []:
                work["contexts"].append({
                    "anchor": anchor_id,
                    "text": text_of(context.get("context")),
                    "intents": [i["id"] for i in context.get("intents", [])],
                })
    return works, per_anchor


def compact(work):
    """Drop context bodies, keep the signal that survives into curation."""
    return {
        "s2_id": work["s2_id"],
        "title": work["title"],
        "year": work["year"],
        "venue": work["venue"],
        "num_cited_by": work["num_cited_by"],
        "fields": work["fields"],
        "authors": [a["name"] for a in work["authors"]],
        "author_s2_ids": [a["s2_author_id"] for a in work["authors"]],
        "cites_anchors": sorted(work["cites_anchors"]),
        "key_on": sorted(a for a, v in work["cites_anchors"].items() if v["is_key"]),
        "intents": sorted({i for c in work["contexts"] for i in c["intents"]}),
        "n_contexts": len(work["contexts"]),
    }


def report(works):
    influential = sum(
        1 for w in works.values() if any(v["is_key"] for v in w["cites_anchors"].values())
    )
    with_context = sum(1 for w in works.values() if w["contexts"])
    intents = Counter(i for w in works.values() for c in w["contexts"] for i in c["intents"])
    breadth = Counter(len(w["cites_anchors"]) for w in works.values())
    print(f"\ndistinct citing works       {len(works)}")
    print(f"influential on >=1 anchor   {influential}")
    print(f"carrying a citation context {with_context}")
    print(f"context intents             {dict(intents)}")
    print(f"works by anchors cited      {dict(sorted(breadth.items()))}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="data/pools/lane_a.json")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    print("harvesting citing works, keyless, from the Semantic Scholar frontend API")
    works, per_anchor = harvest()
    report(works)

    with open(args.out, "w") as handle:
        json.dump({"per_anchor": per_anchor, "works": works}, handle)

    compact_path = args.out.replace(".json", "_compact.json")
    rows = sorted(
        (compact(w) for w in works.values()),
        key=lambda r: (-(r["num_cited_by"] or 0), r["title"]),
    )
    with open(compact_path, "w") as handle:
        json.dump({
            "schema_version": 1,
            "source": "semanticscholar.org frontend citations API (keyless)",
            "n_works": len(rows),
            "per_anchor": per_anchor,
            "works": rows,
        }, handle, indent=0)

    for path in (args.out, compact_path):
        print(f"wrote {path}  ({os.path.getsize(path) / 1e6:.2f} MB)")
    print("\nNot yet merged against the OpenCitations union or the Scholar lane, and the "
          "anchors themselves appear in the pool because they cite each other -- both are "
          "resolve-step work, not harvest-step work.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
