#!/usr/bin/env python3
"""Build authorship edges with a trustworthy affiliation for each.

OpenAlex attaches institutions per work rather than per person, so affiliation
at the time of publication comes free -- which is exactly what the index needs.
The catch is that its institution assignment is wrong often enough to matter.
Measured over this corpus, about 12% of edges carry an institution the paper's
own affiliation string does not support, and the failures are confident rather
than vague:

    'Pleno Inc., San Diego'              -> Drip Research Technology Services
    'UC Berkeley'                        -> Berkeley College (a college in NJ)
    'School of EECS, Peking University'  -> King University  (matched "king")
    'MIT CSAIL'                          -> Vassar College
    'SimpleMachines Inc'                 -> Shell (India)
    'ARM Ltd., Manchester'               -> American Rock Mechanics Association

So the raw affiliation string printed on the paper is treated as ground truth,
and OpenAlex's label is accepted only when the raw string supports it. Anything
neither an alias nor OpenAlex can justify goes to a review queue rather than
into the data.

An acronym rule was tried as a way to rescue legitimate expansions such as
INRIA and CNRS, and rejected: it also "rescued" ARM into the American Rock
Mechanics Association and MIT into the Moscow Institute of Thermal Technology.
Explicit aliases are slower to write and do not misfire.

    export OPENALEX_API_KEY=...        # optional, but avoids the daily budget
    python3 curate/affiliations.py --pool data/pools/lane_a.json \
        --out data/people/authorship.json

DOIs come from two places, neither of them the pool: harvest/artifacts.py's
enrich state, which records them without rewriting the pool, and the
OpenCitations-only list, whose works have no Semantic Scholar id at all.
"""

import argparse
import html
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from collections import Counter, defaultdict

MAILTO = "saman@lcs.mit.edu"
# Read from the environment, never hardcoded: this repository is public.
# Without a key the polite pool still works but shares a daily budget that runs
# out; with one, the 1,700-DOI pass finishes in about twelve seconds.
API_KEY = os.environ.get("OPENALEX_API_KEY")
SELECT = "id,doi,display_name,publication_year,authorships"

# Raw-string patterns mapped to a canonical institution, first match wins.
# Written against the strings that actually appear in this corpus; extend it
# rather than reaching for a general-purpose matcher, because the failures of
# general matching are silent and confident.
ALIASES = [
    (r"\bmit\b|massachusetts institute of tech|\bcsail\b", "Massachusetts Institute of Technology"),
    (r"uc berkeley|university of california,? berkeley", "University of California, Berkeley"),
    (r"peking university|\bpku\b", "Peking University"),
    (r"tsinghua", "Tsinghua University"),
    (r"institute of computing technology", "Institute of Computing Technology, CAS"),
    (r"university of chinese academy", "University of Chinese Academy of Sciences"),
    (r"chinese academy of sciences", "Chinese Academy of Sciences"),
    (r"\binria\b|institut national de recherche en", "INRIA"),
    (r"\bcea\b|commissariat a l", "CEA"),
    (r"\bcnrs\b|centre national de la recherche", "CNRS"),
    (r"\barm ltd|\barm inc|\barm\b(?= *,)", "Arm"),
    (r"\bamd\b|advanced micro devices", "AMD"),
    (r"\bnvidia\b", "NVIDIA"),
    (r"facebook|\bmeta\b(?! *analysis)", "Meta"),
    (r"\bgoogle\b|deepmind", "Google"),
    (r"microsoft", "Microsoft"),
    (r"\badobe\b", "Adobe"),
    (r"\bhuawei\b", "Huawei"),
    (r"william ?(&|and) ?mary", "William & Mary"),
    (r"\bcuhk\b|chinese university of hong kong", "Chinese University of Hong Kong"),
    (r"university of hong kong|\bhku\b", "University of Hong Kong"),
    (r"\bunsw\b|university of new south wales", "UNSW Sydney"),
    (r"sustech|southern university of science and tech", "Southern University of Science and Technology"),
    (r"barcelona supercomputing|\bbsc\b", "Barcelona Supercomputing Center"),
    (r"universit(y|e|at|at) (of )?(gent|ghent)", "Ghent University"),
    (r"m(u|ue)nster", "University of Munster"),
    (r"link(o|oe)ping", "Linkoping University"),
    (r"sun yat-?sen", "Sun Yat-sen University"),
    (r"eth ?zurich", "ETH Zurich"),
    (r"sensetime", "SenseTime"),
    (r"simplemachines", "SimpleMachines"),
    (r"\bpleno\b", "Pleno"),
    (r"stanford", "Stanford University"),
]
ALIASES = [(re.compile(p), c) for p, c in ALIASES]

STOP = set("""university institute technology college school department laboratory
research center centre national state united states inc ltd corporation company
systems science sciences engineering computer computing""".split())


def clean(text):
    """Raw strings arrive HTML-escaped, sometimes twice."""
    return re.sub(r"\s+", " ", html.unescape(html.unescape(text or ""))).strip()


def fold(text):
    stripped = unicodedata.normalize("NFD", text or "")
    return "".join(c for c in stripped if unicodedata.category(c) != "Mn").lower()


def words(text):
    return set(re.findall(r"[a-z]{4,}", fold(text)))


def from_raw(raw):
    folded = fold(clean(raw))
    for pattern, canonical in ALIASES:
        if pattern.search(folded):
            return canonical
    return None


def supported_by(assigned, raws):
    """Does any raw string share a distinctive word with the assigned label?"""
    key = words(assigned) - STOP
    if not key:
        return False
    return any(key & words(clean(raw)) for raw in raws)


def with_key(url):
    return f"{url}&api_key={API_KEY}" if API_KEY else url


def openalex(url, tries=3):
    request = urllib.request.Request(
        url, headers={"User-Agent": f"HalideWorldIndex/0.1 (mailto:{MAILTO})"})
    for attempt in range(tries):
        try:
            return json.load(urllib.request.urlopen(request, timeout=60))
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                return {"_budget": True}
            time.sleep(1.5)
        except Exception:
            time.sleep(1.5)
    return {"_error": True}


def fetch_authorships(dois, cache_path):
    cache = json.load(open(cache_path)) if os.path.exists(cache_path) else {}
    todo = [d for d in dois if d not in cache]
    print(f"{len(cache)} cached, {len(todo)} DOIs to fetch")
    for start in range(0, len(todo), 50):
        batch = todo[start:start + 50]
        url = (f"https://api.openalex.org/works?filter=doi:{'|'.join(batch)}"
               f"&per-page=50&select={SELECT}&mailto={MAILTO}")
        payload = openalex(with_key(url))
        if payload.get("_budget"):
            print("OpenAlex daily budget exhausted. Set OPENALEX_API_KEY, or rerun "
                  "after it resets at midnight UTC.")
            break
        for work in payload.get("results", []):
            doi = (work.get("doi") or "").replace("https://doi.org/", "").lower()
            if doi:
                cache[doi] = work
        if (start // 50) % 6 == 0:
            json.dump(cache, open(cache_path, "w"))
            print(f"  {start + len(batch)}/{len(todo)}")
    json.dump(cache, open(cache_path, "w"))
    return cache


def read_extra_dois(path):
    """Accept a bare list, {"dois": [...]}, or a list of records with a doi field."""
    if not os.path.exists(path):
        return set()
    payload = json.load(open(path))
    if isinstance(payload, dict):
        payload = payload.get("dois") or payload.get("works") or []
    found = set()
    for entry in payload:
        doi = entry.get("doi") if isinstance(entry, dict) else entry
        if doi:
            found.add(str(doi).lower())
    return found


def build_edges(works_by_doi, pool):
    """One edge per author per paper, carrying affiliation at that time."""
    edges = []
    for doi, work in works_by_doi.items():
        year = work.get("publication_year")
        for position, authorship in enumerate(work.get("authorships", [])):
            author = authorship.get("author") or {}
            # Keep EVERY raw string, not just the first: a person listing two
            # affiliations otherwise loses the one that resolves.
            raws = [clean(r) for r in (authorship.get("raw_affiliation_strings") or [])]
            assigned = [i.get("display_name") for i in authorship.get("institutions", [])
                        if i.get("display_name")]

            resolved, basis = None, None
            for raw in raws:
                resolved = from_raw(raw)
                if resolved:
                    basis = "alias"
                    break
            if not resolved and assigned:
                if supported_by(assigned[0], raws) or not raws:
                    resolved, basis = assigned[0], "openalex-supported"
                else:
                    basis = "unresolved"
            elif not resolved:
                basis = "no-institution"

            edges.append({
                "doi": doi,
                "year": year,
                "name": author.get("display_name"),
                "openalex_author": author.get("id"),
                "orcid": author.get("orcid"),
                "position": position,
                "affiliation": resolved,
                "basis": basis,
                "openalex_said": assigned[0] if assigned else None,
                "raw": raws[0] if raws else None,
            })
    return edges


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pool", default="data/pools/lane_a.json")
    parser.add_argument("--out", default="data/people/authorship.json")
    parser.add_argument("--cache", default="data/people/openalex_cache.json")
    parser.add_argument("--enrich-state", default="data/pools/artifacts_state.json",
                        help="where harvest/artifacts.py recorded each work's DOI")
    parser.add_argument("--extra-dois", default="data/pools/opencitations_only.json",
                        help="further DOIs to include, e.g. works found only by "
                             "OpenCitations and so absent from the S2 pool")
    args = parser.parse_args()
    sys.stdout.reconfigure(line_buffering=True)

    pool = json.load(open(args.pool))
    works = pool["works"] if isinstance(pool.get("works"), dict) else {
        w["s2_id"]: w for w in pool["works"]}
    # DOIs are not in the pool. harvest/artifacts.py records them in its own
    # enrich state and never rewrites the pool, so read them from there and
    # fall back to the pool for any that were attached some other way.
    dois = {(w.get("doi") or "").lower() for w in works.values() if w.get("doi")}
    if os.path.exists(args.enrich_state):
        enriched = json.load(open(args.enrich_state)).get("enrich", {})
        dois |= {v["doi"].lower() for v in enriched.values() if v.get("doi")}
        print(f"{len(enriched)} works in {args.enrich_state}")
    extra = read_extra_dois(args.extra_dois)
    if extra:
        print(f"{len(extra)} extra DOIs from {args.extra_dois}")
        dois |= extra
    dois = sorted(d for d in dois if d)
    if not dois:
        print(f"no DOIs found. They are written by harvest/artifacts.py --phase enrich "
              f"into {args.enrich_state}; pass --enrich-state if it lives elsewhere.")
        return 1
    print(f"{len(dois)} distinct DOIs"
          f"{' (using OPENALEX_API_KEY)' if API_KEY else ' (polite pool, no key)'}")

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    os.makedirs(os.path.dirname(args.cache) or ".", exist_ok=True)
    cache = fetch_authorships(dois, args.cache)
    edges = build_edges(cache, works)

    basis = Counter(e["basis"] for e in edges)
    # Only count a relabelling as a correction when OpenAlex's label was
    # actually unsupported; an alias that merely tidies a name is not one.
    corrections = Counter(
        f'{e["openalex_said"]} -> {e["affiliation"]}'
        for e in edges
        if e["basis"] == "alias" and e["openalex_said"]
        and not supported_by(e["openalex_said"], [e["raw"] or ""])
        and e["openalex_said"] != e["affiliation"]
    )
    people = defaultdict(list)
    for edge in edges:
        if edge["openalex_author"]:
            people[edge["openalex_author"]].append(edge)

    print(f"\nedges {len(edges)}  people {len(people)}")
    print("resolution basis:", dict(basis))
    print("\ncorrections made against OpenAlex:")
    for label, count in corrections.most_common(15):
        print(f"  {count:4d}  {label}")

    review = [e for e in edges if e["basis"] == "unresolved"]
    with open(args.out, "w") as handle:
        json.dump({"schema_version": 1, "n_edges": len(edges),
                   "n_people": len(people), "edges": edges}, handle, indent=0)
    review_path = args.out.replace(".json", "_review.json")
    with open(review_path, "w") as handle:
        json.dump(sorted(
            Counter((e["raw"], e["openalex_said"]) for e in review).items(),
            key=lambda kv: -kv[1]), handle, indent=1)
    print(f"\nwrote {args.out} and {review_path} ({len(review)} edges need review)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
