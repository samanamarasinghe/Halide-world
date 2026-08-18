#!/usr/bin/env python3
"""Tell a paper's OWN artifact apart from every other repository it mentions.

The harvest pass records every URL in a PDF, which conflates three very
different things: the artifact the authors released, the dependencies they built
on, and the systems they merely cite. Across the Halide corpus that inflated
"papers with artifacts" badly -- the most frequently named repositories were
nvidia/cutlass, google/jax and onnx, none of which is anyone's artifact.

Attribution uses three signals drawn from the PDF text around each URL:

  * cue phrases   "available at", "artifact", "we release", "our
                  implementation" within a window before the link
  * name overlap  the owner or repository name shares a distinctive token with
                  the paper's title, or matches an author surname
  * position      links after the References heading are bibliography, and
                  bibliography links are almost never the paper's own artifact

Requires the PDFs kept by `harvest/artifacts.py --keep-pdfs`. Nothing is
re-downloaded.

    python3 curate/attribute_artifacts.py --pool data/pools/lane_a.json \
        --pdf-dir data/pdfs --out data/pools/artifacts_attributed.json
"""

import argparse
import json
import os
import re
import sys
from collections import Counter

# GitHub paths that are not repositories. `features/copilot` showed up in four
# papers before this list existed.
NON_REPO_OWNERS = {
    "features", "about", "blog", "topics", "marketplace", "sponsors", "orgs",
    "settings", "pricing", "security", "readme", "explore", "collections",
    "events", "site", "customer-stories", "enterprise", "login", "join",
}

ARTIFACT_CUES = [
    "artifact", "available at", "publicly available", "is available",
    "are available", "we release", "released at", "open-source", "open source",
    "our implementation", "our prototype", "source code", "code is at",
    "can be found at", "we have made", "reproduce", "supplementary",
]
CUE_WINDOW = 260  # characters before the URL to search for a cue

REPO_RE = re.compile(
    r"(?:https?://)?(?:www\.)?github\.com/([\w.-]+)/([\w.-]+)", re.I)
REFERENCES_RE = re.compile(r"\n\s*(references|bibliography)\s*\n", re.I)
STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "using", "via", "a",
    "an", "of", "on", "in", "to", "by", "code", "based", "towards", "toward",
    "efficient", "fast", "high", "performance", "language", "compiler",
    "compilation", "programming", "system", "systems", "framework", "approach",
    "optimization", "optimisation", "optimizing", "scheduling", "schedule",
    "parallel", "automatic", "learning", "neural", "deep", "data", "new",
}


def extract_text(path):
    try:
        from pypdf import PdfReader
    except ImportError:
        return None
    try:
        return "\n".join((page.extract_text() or "")
                         for page in PdfReader(path).pages)
    except Exception:
        return None


def title_tokens(title):
    tokens = re.findall(r"[a-z0-9]+", (title or "").lower())
    return {t for t in tokens if len(t) > 2 and t not in STOPWORDS}


def surnames(authors):
    out = set()
    for author in authors or []:
        name = author if isinstance(author, str) else author.get("name", "")
        parts = re.findall(r"[A-Za-z]{3,}", name)
        if parts:
            out.add(parts[-1].lower())
    return out


def slug_tokens(owner, repo):
    """Split a slug into comparable tokens: exo2-artifact -> {exo2, exo, artifact}."""
    raw = re.split(r"[-_.]+", f"{owner} {repo}".lower())
    tokens = set()
    for part in raw:
        if len(part) > 2:
            tokens.add(part)
            stripped = part.rstrip("0123456789")
            if len(stripped) > 2:
                tokens.add(stripped)
    return tokens


def find_links(text):
    """Every GitHub repo reference with its character offset."""
    found = []
    for match in REPO_RE.finditer(text):
        owner, repo = match.group(1).lower(), match.group(2).lower()
        repo = re.sub(r"(\.git)+$", "", repo).rstrip(".-")
        if not repo or owner in NON_REPO_OWNERS:
            continue
        found.append({"owner": owner, "repo": repo, "at": match.start(),
                      "truncated": match.group(0).endswith("-")})
    return found


def references_offset(text):
    matches = list(REFERENCES_RE.finditer(text))
    return matches[-1].start() if matches else None


def score_link(link, text, refs_at, tokens, names):
    """Positive score means the paper's own artifact."""
    score = 0
    reasons = []

    window = text[max(0, link["at"] - CUE_WINDOW):link["at"]].lower()
    cue = next((c for c in ARTIFACT_CUES if c in window), None)
    if cue:
        score += 3
        reasons.append(f"cue:{cue}")

    overlap = slug_tokens(link["owner"], link["repo"]) & tokens
    if overlap:
        score += 3
        reasons.append("title:" + ",".join(sorted(overlap)[:2]))

    # An owner matching an author surname is a personal account publishing the
    # work; a repo name matching one is weaker. Systems are often named nothing
    # like their paper title (Etch, in "Correct Compilation of Semiring
    # Contractions"), so this is frequently the only name signal available.
    if link["owner"] in names:
        score += 3
        reasons.append("author-owner")
    elif link["repo"] in names:
        score += 2
        reasons.append("author-repo")

    if "artifact" in link["repo"] or "artifact" in link["owner"]:
        score += 2
        reasons.append("named-artifact")

    if refs_at is not None and link["at"] > refs_at:
        score -= 3
        reasons.append("in-bibliography")

    return score, reasons


def classify(score):
    if score >= 3:
        return "own_artifact"
    if score >= 1:
        return "possible_artifact"
    return "mentioned"


def collapse_truncated(best):
    """Fold line-break fragments into the full slug.

    A URL split across lines yields `exo-lang/exo2` alongside
    `exo-lang/exo2-artifact`. Only fold a slug that was seen truncated at least
    once and is a strict prefix of a longer one -- `exo-lang/exo` is a prefix of
    `exo-lang/exo2-artifact` but is a different repository, and it is never seen
    with a trailing hyphen.
    """
    slugs = sorted(best, key=len, reverse=True)
    kept = []
    for slug in slugs:
        if best[slug].get("truncated") and any(k.startswith(slug) for k in kept):
            continue
        kept.append(slug)
    return sorted((best[k] for k in kept), key=lambda r: -r["score"])


def attribute(work, pdf_path):
    text = extract_text(pdf_path)
    if not text:
        return None
    tokens = title_tokens(work.get("title") if isinstance(work.get("title"), str)
                          else (work.get("title") or {}).get("text", ""))
    names = surnames(work.get("authors"))
    refs_at = references_offset(text)

    best = {}
    for link in find_links(text):
        slug = f"{link['owner']}/{link['repo']}"
        score, reasons = score_link(link, text, refs_at, tokens, names)
        if slug not in best:
            best[slug] = {"repo": slug, "score": score, "reasons": reasons,
                          "truncated": link["truncated"]}
        else:
            if score > best[slug]["score"]:
                best[slug].update(score=score, reasons=reasons)
            # Seen unbroken anywhere means it is not a fragment.
            best[slug]["truncated"] &= link["truncated"]
    rows = collapse_truncated(best)
    for row in rows:
        row["verdict"] = classify(row["score"])
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pool", default="data/pools/lane_a.json")
    parser.add_argument("--pdf-dir", default="data/pdfs")
    parser.add_argument("--out", default="data/pools/artifacts_attributed.json")
    args = parser.parse_args()
    sys.stdout.reconfigure(line_buffering=True)

    pool = json.load(open(args.pool))
    works = pool["works"] if isinstance(pool.get("works"), dict) else {
        w["s2_id"]: w for w in pool["works"]
    }

    pdfs = [f for f in os.listdir(args.pdf_dir) if f.endswith(".pdf")]
    print(f"{len(pdfs)} PDFs on disk, pool has {len(works)} works")

    papers, tally = [], Counter()
    for n, filename in enumerate(sorted(pdfs), 1):
        s2_id = filename[:-4]
        rows = attribute(works.get(s2_id, {}), os.path.join(args.pdf_dir, filename))
        if rows is None:
            tally["unreadable"] += 1
            continue
        owned = [r for r in rows if r["verdict"] == "own_artifact"]
        tally["own artifact found" if owned else "no own artifact"] += 1
        if rows:
            work = works.get(s2_id, {})
            title = work.get("title")
            papers.append({
                "s2_id": s2_id,
                "title": title if isinstance(title, str) else (title or {}).get("text", ""),
                "year": work.get("year"),
                "own_artifacts": [r["repo"] for r in owned],
                "links": rows,
            })
        if n % 200 == 0:
            print(f"  {n}/{len(pdfs)}")

    with open(args.out, "w") as handle:
        json.dump({"schema_version": 1, "n_papers": len(papers),
                   "n_with_own_artifact": tally["own artifact found"],
                   "papers": papers}, handle, indent=0)

    verdicts = Counter(r["verdict"] for p in papers for r in p["links"])
    print(f"\n{dict(tally)}")
    print(f"links by verdict: {dict(verdicts)}")
    print(f"papers with an identified own artifact: {tally['own artifact found']}")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
