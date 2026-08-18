#!/usr/bin/env python3
"""Find the code artifacts behind the papers in the Lane A pool.

Semantic Scholar carries no repository links at all, so the only route to a
paper's artifact is the paper itself. This runs in three phases, each resumable,
and is meant to be left alone for a few hours:

  1. enrich   ask the Semantic Scholar detail endpoint for each work's DOI,
              open-access status and candidate PDF links (~5 minutes)
  2. fetch    download each reachable PDF, extract its text, harvest every URL
              in it (hours)
  3. resolve  classify the harvested URLs into artifact candidates

Phase 2 discards each PDF after extraction by default, since the text is all the
artifact pass needs. Pass --keep-pdfs to save them instead -- worth it, because
full-text curation later wants the papers anyway, and a kept PDF is re-read from
disk rather than re-downloaded on any rerun. Budget about 1.3 MB per paper,
roughly 2 GB in total.

    pip install pypdf
    python3 harvest/artifacts.py --pool data/pools/lane_a.json \
        --out data/pools/artifacts.json --keep-pdfs

Interrupt it freely. State lives in <out>_state.json and every phase skips work
already done, so re-running continues rather than restarting.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections import Counter

BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
S2_API = "https://www.semanticscholar.org/api/1/paper"

# Hosts that actually carry research artifacts.
ARTIFACT_HOSTS = [
    ("github", r"github\.com/[\w.-]+/[\w.-]+"),
    ("gitlab", r"gitlab\.[\w.-]+/[\w.-]+/[\w.-]+"),
    ("bitbucket", r"bitbucket\.org/[\w.-]+/[\w.-]+"),
    ("zenodo", r"zenodo\.org/(?:record|records|doi)/[\w./-]+"),
    ("figshare", r"figshare\.com/[\w./-]+"),
    ("osf", r"osf\.io/[\w]+"),
    ("dryad", r"datadryad\.org/[\w./-]+"),
    ("codeocean", r"codeocean\.com/capsule/[\w./-]+"),
    ("zenodo_doi", r"doi\.org/10\.5281/zenodo\.\d+"),
    # ACM DOIs are deliberately NOT listed: every paper's bibliography is full of
    # them, so they match dozens of times per paper and mean nothing.
]

# URLs that appear in nearly every paper and mean nothing.
URL_NOISE = re.compile(
    r"(creativecommons\.org|doi\.org/10\.1145/\d+$|acm\.org/publications"
    r"|springer\.com|ieee\.org|arxiv\.org/abs|orcid\.org|w3\.org"
    r"|latex-project|overleaf|fonts\.googleapis)", re.I,
)
URL_RE = re.compile(r"https?://[^\s<>\"'()\[\],;]+", re.I)


def text_of(field):
    if isinstance(field, dict):
        return field.get("text", "") or ""
    return field or ""


def get_json(url, referer_id, tries=4):
    headers = {
        "User-Agent": BROWSER_UA,
        "Accept": "application/json",
        "Referer": f"https://www.semanticscholar.org/paper/{referer_id}",
    }
    for attempt in range(tries):
        try:
            request = urllib.request.Request(url, headers=headers)
            return json.load(urllib.request.urlopen(request, timeout=45))
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 503):
                time.sleep(2 + 2 * attempt)
                continue
            return {"_error": f"HTTP {exc.code}"}
        except Exception:
            time.sleep(1.5)
    return {"_error": "gave up"}


def load_state(path):
    return json.load(open(path)) if os.path.exists(path) else {"enrich": {}, "fetch": {}}


def save_state(state, path):
    with open(path, "w") as handle:
        json.dump(state, handle)


# ---------------------------------------------------------------- phase 1

def enrich(works, state, state_path):
    todo = [k for k in works if k not in state["enrich"]]
    print(f"[enrich] {len(state['enrich'])} done, {len(todo)} to go")
    for n, s2_id in enumerate(todo, 1):
        payload = get_json(f"{S2_API}/{s2_id}", s2_id)
        if "_error" in payload:
            state["enrich"][s2_id] = payload
        else:
            paper = payload["paper"]
            links = (paper.get("links") or []) + (paper.get("alternatePaperLinks") or [])
            state["enrich"][s2_id] = {
                "doi": (paper.get("doiInfo") or {}).get("doi"),
                "oa_license": (paper.get("openAccessInfo") or {}).get("license"),
                "links": [{"type": l.get("linkType"), "url": l.get("url")} for l in links],
            }
        if n % 200 == 0:
            save_state(state, state_path)
            print(f"[enrich]   {n}/{len(todo)}")
    save_state(state, state_path)
    have = sum(1 for v in state["enrich"].values() if v.get("doi"))
    print(f"[enrich] complete: {have} works carry a DOI")


def pdf_candidates(record):
    """Links worth trying, best first. arXiv needs its /pdf/ form."""
    out = []
    for link in record.get("links", []):
        url, kind = link.get("url") or "", link.get("type")
        if not url:
            continue
        if kind == "arxiv" and "/abs/" in url:
            out.append(url.replace("/abs/", "/pdf/"))
        elif kind in ("openaccess", "anansi", "crawler", "arxiv"):
            out.append(url)
    return list(dict.fromkeys(out))[:4]


# ---------------------------------------------------------------- phase 2

def extract_text(path):
    try:
        from pypdf import PdfReader
    except ImportError:
        return None, "pypdf missing -- pip install pypdf"
    try:
        reader = PdfReader(path)
        return "\n".join((page.extract_text() or "") for page in reader.pages), None
    except Exception as exc:
        return None, f"extract failed: {type(exc).__name__}"


def fetch_text(url, keep_path=None):
    """Download to a temp file, verify it really is a PDF, extract, then either
    move it to keep_path or discard it.

    Fetching to a temp name matters: retrying straight into the destination can
    overwrite a good download with an error page on the second attempt. The move
    to keep_path only happens after the %PDF check passes, so a kept file is
    always a real PDF.
    """
    handle, tmp = tempfile.mkstemp(suffix=".pdf")
    os.close(handle)
    moved = False
    try:
        result = subprocess.run(
            ["curl", "-sSL", "-m", "90", "-A", BROWSER_UA, "-o", tmp, url],
            capture_output=True,
        )
        if result.returncode != 0 or os.path.getsize(tmp) < 1000:
            return None, "download failed"
        with open(tmp, "rb") as fh:
            if fh.read(4) != b"%PDF":
                return None, "not a pdf"
        text, error = extract_text(tmp)
        if keep_path:
            os.makedirs(os.path.dirname(keep_path) or ".", exist_ok=True)
            shutil.move(tmp, keep_path)
            moved = True
        return text, error
    finally:
        if not moved and os.path.exists(tmp):
            os.remove(tmp)


def harvest_urls(text):
    found = []
    for match in URL_RE.findall(text or ""):
        url = match.rstrip(".,;:)]}").replace("\n", "")
        if URL_NOISE.search(url):
            continue
        found.append(url)
    return list(dict.fromkeys(found))[:60]


def fetch(works, state, state_path, keep_pdfs=False, pdf_dir="data/pdfs"):
    reachable = [k for k, v in state["enrich"].items() if pdf_candidates(v)]
    todo = [k for k in reachable if k not in state["fetch"]]
    print(f"[fetch] {len(reachable)} works have a candidate link; "
          f"{len(state['fetch'])} done, {len(todo)} to go")
    if keep_pdfs:
        print(f"[fetch] keeping PDFs in {pdf_dir}/ (~1.3 MB each, about 2 GB in total)")
    started = time.time()
    for n, s2_id in enumerate(todo, 1):
        text, error = None, "no candidate"
        keep_path = os.path.join(pdf_dir, f"{s2_id}.pdf") if keep_pdfs else None
        # A PDF already on disk is re-read rather than re-downloaded, so a rerun
        # after clearing fetch state costs no network at all.
        if keep_path and os.path.exists(keep_path):
            text, error = extract_text(keep_path)
        else:
            for url in pdf_candidates(state["enrich"][s2_id]):
                text, error = fetch_text(url, keep_path)
                if text:
                    break
        state["fetch"][s2_id] = (
            {"urls": harvest_urls(text), "chars": len(text)} if text else {"error": error}
        )
        if n % 25 == 0:
            save_state(state, state_path)
            rate = n / (time.time() - started)
            left = (len(todo) - n) / rate / 60 if rate else 0
            ok = sum(1 for v in state["fetch"].values() if "urls" in v)
            print(f"[fetch]   {n}/{len(todo)}  ok {ok}  {rate:.2f}/s  ~{left:.0f} min left")
    save_state(state, state_path)


# ---------------------------------------------------------------- phase 3

def dedupe_artifacts(hits):
    """Collapse the same artifact appearing in several forms.

    PDF text extraction breaks URLs across lines, so one repository surfaces as
    both `exo-lang/exo2-` and `exo-lang/exo2-artifact` in the same paper. Only a
    URL that ended in a hyphen is treated as truncated and folded into a longer
    one. Plain prefix matching cannot be used: `exo-lang/exo` is a prefix of
    `exo-lang/exo2-artifact` and they are different repositories.
    """
    entries = {}
    for hit in hits:
        raw = hit["url"]
        truncated = raw.endswith("-")
        url = re.sub(r"(\.git|/)+$", "", raw.rstrip("-.")).lower()
        if not url:
            continue
        # A URL seen unbroken anywhere in the paper is not truncated.
        if url in entries:
            entries[url]["truncated"] &= truncated
        else:
            entries[url] = {"kind": hit["kind"], "truncated": truncated}
    kept = []
    for url, meta in sorted(entries.items(), key=lambda kv: -len(kv[0])):
        if meta["truncated"] and any(other.startswith(url) for other in kept):
            continue
        kept.append(url)
    return [{"kind": entries[u]["kind"], "url": u} for u in sorted(kept)]


def resolve(works, state, out_path):
    rows = []
    tally = Counter()
    for s2_id, result in state["fetch"].items():
        if "urls" not in result:
            tally[result.get("error", "failed")] += 1
            continue
        hits = []
        for url in result["urls"]:
            for kind, pattern in ARTIFACT_HOSTS:
                match = re.search(pattern, url, re.I)
                if match:
                    hits.append({"kind": kind, "url": match.group(0)})
                    break
        unique = dedupe_artifacts(hits)
        tally["artifact found" if unique else "no artifact link"] += 1
        if unique:
            work = works.get(s2_id, {})
            rows.append({
                "s2_id": s2_id,
                "title": text_of(work.get("title")),
                "year": work.get("year"),
                "doi": state["enrich"].get(s2_id, {}).get("doi"),
                "artifacts": unique,
            })
    rows.sort(key=lambda r: -(r["year"] or 0))
    with open(out_path, "w") as handle:
        json.dump({"schema_version": 1, "n_papers_with_artifacts": len(rows),
                   "papers": rows}, handle, indent=0)
    print(f"\n[resolve] {dict(tally)}")
    print(f"[resolve] papers with at least one artifact link: {len(rows)}")
    print("[resolve] by host:",
          dict(Counter(a["kind"] for r in rows for a in r["artifacts"])))
    print(f"[resolve] wrote {out_path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pool", default="data/pools/lane_a.json")
    parser.add_argument("--out", default="data/pools/artifacts.json")
    parser.add_argument("--keep-pdfs", action="store_true",
                        help="save each PDF instead of discarding it after extraction")
    parser.add_argument("--pdf-dir", default="data/pdfs")
    parser.add_argument("--phase", choices=["enrich", "fetch", "resolve"],
                        help="run a single phase instead of all three")
    args = parser.parse_args()

    pool = json.load(open(args.pool))
    works = pool["works"] if isinstance(pool.get("works"), dict) else {
        w["s2_id"]: w for w in pool["works"]
    }
    print(f"pool: {len(works)} works")

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    state_path = args.out.replace(".json", "_state.json")
    state = load_state(state_path)

    if args.phase in (None, "enrich"):
        enrich(works, state, state_path)
    if args.phase in (None, "fetch"):
        fetch(works, state, state_path, args.keep_pdfs, args.pdf_dir)
    if args.phase in (None, "resolve"):
        resolve(works, state, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
