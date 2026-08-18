#!/usr/bin/env python3
"""Enumerate every GitHub repository that shows a Halide code signature.

GitHub's code search API caps any single query at 1000 results and serves 100
per page, while a bare `"Halide.h"` matches ~9,500 files. The workaround is to
shard each signature by file size into ranges that individually stay under the
cap, then page through each shard. Sharding is adaptive: a range that still
reports 1000+ results is split in half and retried.

Requires a token, because code search is not available unauthenticated:

    export GITHUB_TOKEN=ghp_...
    python3 harvest/github_repos.py --out data/pools/lane_b.json

Authenticated code search allows 10 requests/minute, so a full run takes on the
order of 20 minutes. It is resumable -- re-running skips completed shards. Pass
--only <signature name> to redo a single signature: its shard markers are
dropped and everything it recorded previously is purged, so a corrected query
replaces its old results instead of adding to them.

A note on quoting, learned the hard way twice. A signature may contain at most
ONE pair of quotes, with no interior quotes. Backslash-escaped inner quotes
(`"#include \"Halide.h\""`) return zero for every shard. So do nested bare
quotes (`"#include "Halide.h""`), because the third quote opens a fresh phrase
that swallows the trailing qualifiers -- the query ends up searching for the
literal text `NOT is:fork size:0..500`. Regex literals (`/#include "Halide\.h"/`)
are not supported by this REST endpoint either. The working form is a single
quoted phrase: `"Halide.h"` returns 2,888 hits in the 1-2KB shard alone. This is
why the include signature searches for the bare header name rather than the full
include line, and why it is weighted `source` rather than treated as proof of
use. A broken query is indistinguishable from an unused signature -- both report
zero -- so spot-check every new signature against the API before a full run.

Two things the results will contain that curation has to handle. Vendored
bundles match the source signatures without using Halide -- OpenCV ships a
Halide backend, so every project that vendors OpenCV sources appears, and that
is roughly 70% of the raw pool. And prose about Halide matches too: any repo
whose documentation quotes a signature string will show up, including our own
notes. Classification should key on the matched PATH, not the repo name:
`find_package(Halide` at `CMakeLists.txt` is a consumer, the same line at
`.../opencv/cmake/OpenCVDetectHalide.cmake` is not.
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter

API = "https://api.github.com/search/code"
PER_PAGE = 100
RESULT_CAP = 1000
RATE_SLEEP = 6.5  # 10 requests/minute, with headroom

# Ordered strongest to weakest. `weight` records how much a match means: a
# CMake consumer line is far better evidence of *using* Halide than a header
# reference, because vendored copies of Halide itself carry the headers too.
SIGNATURES = [
    {"name": "cmake_find_package", "query": '"find_package(Halide"', "weight": "consumer"},
    {"name": "cmake_add_library", "query": '"add_halide_library("', "weight": "consumer"},
    {"name": "generator_macro", "query": '"HALIDE_REGISTER_GENERATOR"', "weight": "generator"},
    {"name": "include_header", "query": '"Halide.h"', "weight": "source"},
    {"name": "cpp_func", "query": '"Halide::Func"', "weight": "source"},
    {"name": "cpp_buffer", "query": '"Halide::Buffer"', "weight": "source"},
    {"name": "runtime_header", "query": '"HalideBuffer.h"', "weight": "runtime"},
    {"name": "python_import", "query": '"import halide as hl"', "weight": "python"},
]

# Size ranges in bytes. Deliberately fine-grained at the small end, where source
# files cluster; the adaptive split handles anything still over the cap.
INITIAL_RANGES = [
    (0, 500), (500, 1000), (1000, 2000), (2000, 3000), (3000, 5000),
    (5000, 8000), (8000, 12000), (12000, 20000), (20000, 40000),
    (40000, 100000), (100000, None),
]


def request(url, token, tries=5):
    headers = {
        "Accept": "application/vnd.github.text-match+json",
        "User-Agent": "HalideWorldIndex/0.1",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(
                urllib.request.Request(url, headers=headers), timeout=60
            ) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code in (403, 429):  # secondary rate limit
                wait = 20 * (attempt + 1)
                print(f"    rate limited, sleeping {wait}s")
                time.sleep(wait)
                continue
            if exc.code == 422:  # query rejected, usually an over-long range
                return {"_invalid": True}
            raise
        except Exception:
            time.sleep(5)
    return {"_error": True}


def search(query, token, page=1):
    url = f"{API}?q={urllib.parse.quote(query)}&per_page={PER_PAGE}&page={page}"
    result = request(url, token)
    time.sleep(RATE_SLEEP)
    return result


def size_clause(low, high):
    return f"size:>={low}" if high is None else f"size:{low}..{high}"


def harvest_shard(signature, low, high, token, hits):
    """Page through one size shard. Returns False if it needs splitting."""
    query = f'{signature["query"]} NOT is:fork {size_clause(low, high)}'
    first = search(query, token)
    if first.get("_invalid") or first.get("_error"):
        return True
    total = first.get("total_count", 0)
    if total > RESULT_CAP and high is not None and high - low > 1:
        return False  # split
    pages = min((total + PER_PAGE - 1) // PER_PAGE, RESULT_CAP // PER_PAGE)
    for page in range(1, pages + 1):
        payload = first if page == 1 else search(query, token, page)
        for item in payload.get("items", []):
            repo = (item.get("repository") or {}).get("full_name")
            if not repo:
                continue
            record = hits.setdefault(repo, {"repo": repo, "signatures": {}, "paths": []})
            record["signatures"].setdefault(signature["name"], 0)
            record["signatures"][signature["name"]] += 1
            if len(record["paths"]) < 6:
                record["paths"].append(f'{signature["name"]}:{item.get("path")}')
    print(f"    {size_clause(low, high):22s} total {total:5d}  repos so far {len(hits)}")
    return True


def harvest(token, out_path, only=None):
    state_path = out_path.replace(".json", "_state.json")
    state = json.load(open(state_path)) if os.path.exists(state_path) else {}
    hits = state.get("hits", {})
    done = set(state.get("done", []))

    if only:
        # Drop this signature's shard markers AND purge whatever it recorded
        # last time. Without the purge, a corrected query only ADDS to the wrong
        # results it was meant to replace.
        done = {k for k in done if not k.startswith(f"{only}:")}
        for repo, record in list(hits.items()):
            record["signatures"].pop(only, None)
            record["paths"] = [p for p in record["paths"] if not p.startswith(f"{only}:")]
            if not record["signatures"]:
                del hits[repo]
        print(f"purged prior {only} results; {len(hits)} repos remain from other signatures")

    for signature in SIGNATURES:
        if only and signature["name"] != only:
            continue
        print(f"\n{signature['name']}  ({signature['weight']})")
        queue = list(INITIAL_RANGES)
        while queue:
            low, high = queue.pop(0)
            key = f"{signature['name']}:{low}:{high}"
            if key in done:
                continue
            if harvest_shard(signature, low, high, token, hits):
                done.add(key)
            else:
                middle = (low + high) // 2
                print(f"    {size_clause(low, high)} over cap, splitting at {middle}")
                queue[:0] = [(low, middle), (middle, high)]
            json.dump({"hits": hits, "done": sorted(done)}, open(state_path, "w"))

    return hits


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="data/pools/lane_b.json")
    parser.add_argument("--only", help="re-run a single signature by name")
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("set GITHUB_TOKEN first: code search is not available unauthenticated")
        return 1

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    hits = harvest(token, args.out, args.only)

    # A repo matching a consumer signature builds against Halide; one matching
    # only source signatures may simply be a vendored copy of Halide itself.
    weights = {s["name"]: s["weight"] for s in SIGNATURES}
    for record in hits.values():
        kinds = {weights[n] for n in record["signatures"]}
        record["evidence"] = "consumer" if "consumer" in kinds else (
            "generator" if "generator" in kinds else sorted(kinds)[0]
        )
        record["n_matches"] = sum(record["signatures"].values())

    rows = sorted(hits.values(), key=lambda r: -r["n_matches"])
    with open(args.out, "w") as handle:
        json.dump({"schema_version": 1, "n_repos": len(rows), "repos": rows}, handle, indent=0)

    print(f"\ndistinct repositories {len(rows)}")
    print("by strongest evidence", dict(Counter(r["evidence"] for r in rows)))
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
