#!/usr/bin/env python3
"""Separate real Halide EVIDENCE from reference-list lines in the extracted full text.

`data/pools/fulltext_state.json` gives every sentence in a paper's PDF that mentions
Halide. Not all of them are evidence. A paper's own bibliography contains the Halide
paper's title verbatim, so a paper that merely cites Halide and never discusses it still
comes back with "Halide sentences" and reads, downstream, exactly like a user.

This is the same shape as an earlier finding on this project: ACM DOIs matched 61 times
across 12 papers, because that is every bibliography.

Per paper the classification is:

    body            at least one hit that is not a reference line  -> real evidence
    bibliography    EVERY hit is a reference line                  -> citation-only
    none            no hit at all                                  -> citation-only

`bibliography` and `none` together are the citation-only population, and it is much larger
than the "no hit" count alone suggests.

TWO DETECTORS, AND THE GAP BETWEEN THEM IS THE HONEST UNCERTAINTY:

    venue   venue and pagination tails only (ACM Trans, In Proceedings, pp. 12-34, vol.).
            Conservative: misses a bare title with no venue tail.
    title   the above plus the verbatim titles of the Halide papers themselves, which is
            what a reference entry actually looks like when the venue is on the next line.

On this corpus they disagree sharply -- 54 papers vs 207 -- so the script reports both and
picks neither. Do not quote one number without saying which detector produced it.

    NOT used as a signal: `arXiv:` on its own. It appears in the page-margin stamp of
    every arXiv preprint ("arXiv:1610.09405v1 [cs.SE] 28 Oct 2016"), which lands in body
    sentences and flagged them as citations.

Known imprecision, stated rather than hidden: sentence splitting sometimes joins a body
sentence to the reference that follows it, and a body sentence may legitimately quote the
paper's title. The paper-level rule tolerates both, because a paper is only called
citation-only when EVERY one of its hits is a reference line.

    python3 curate/fulltext_evidence.py --out data/pools/fulltext_evidence.json
"""
import argparse
import json
import re

VENUE = re.compile(
    r"ACM Trans|IEEE Trans|In Proc|Proceedings of|pp\.\s*\d|doi:|SIGPLAN Not|vol\.\s*\d",
    re.I,
)
# The anchor papers' own titles. A reference entry is often just this, with the venue
# wrapped onto the following line and therefore into a different "sentence".
TITLE = re.compile(
    r"language and compiler for optimizing parallelism"
    r"|automatically scheduling halide"
    r"|learning to optimize halide"
    r"|differentiable programming for image processing"
    r"|halide.{0,3}s scheduling language",
    re.I,
)


def is_reference(sentence, use_title):
    if VENUE.search(sentence):
        return True
    return bool(use_title and TITLE.search(sentence))


def classify(hits, use_title):
    if not hits:
        return "none"
    if all(is_reference(s, use_title) for s in hits):
        return "bibliography"
    return "body"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fulltext", default="data/pools/fulltext_state.json")
    ap.add_argument("--out")
    args = ap.parse_args()

    with open(args.fulltext) as f:
        papers = json.load(f)

    out, counts = {}, {}
    for detector in ("venue", "title"):
        use_title = detector == "title"
        tally = {"body": 0, "bibliography": 0, "none": 0}
        for pid, rec in papers.items():
            verdict = classify(rec.get("halide_hits") or [], use_title)
            tally[verdict] += 1
            out.setdefault(pid, {})[detector] = verdict
        counts[detector] = tally

    print(f"papers: {len(papers)}")
    for detector, tally in counts.items():
        cite_only = tally["bibliography"] + tally["none"]
        print(f"  detector {detector:<6} body {tally['body']:5d}  "
              f"bibliography-only {tally['bibliography']:4d}  no hit {tally['none']:4d}"
              f"   -> citation-only {cite_only}")
    disagree = sum(1 for v in out.values() if v["venue"] != v["title"])
    print(f"papers the two detectors classify differently: {disagree} "
          f"-- that spread is the uncertainty, not a number to pick from")

    if args.out:
        with open(args.out, "w") as f:
            json.dump({
                "schema_version": 1,
                "note": "body = at least one non-reference Halide sentence. bibliography = "
                        "every hit is a reference line. none = no hit. The last two are the "
                        "citation-only population.",
                "counts": counts,
                "papers": out,
            }, f, indent=1)
        print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
