#!/usr/bin/env python3
"""Separate real Halide EVIDENCE from reference-list lines in the extracted full text.

`data/pools/fulltext_state.json` gives every sentence in a paper's PDF that mentions
Halide. Not all of them are evidence. A paper's own bibliography contains the Halide
paper's title verbatim, so a paper that merely cites Halide and never discusses it comes
back with "Halide sentences" and reads, downstream, exactly like a user.

Same shape as an earlier finding on this project: ACM DOIs matched 61 times across 12
papers, because that is every bibliography.

Per paper:

    body            at least one hit that is not a reference line  -> real evidence
    bibliography    EVERY hit is a reference line                  -> citation-only
    none            no hit at all                                  -> citation-only

Measured on 1,062 papers: **body 804, bibliography 197, none 61 -> citation-only 258**,
against the 61 that a raw hit count would report.

FOUR SIGNALS, EACH ADDED BECAUSE THE PREVIOUS SET GOT A REAL CASE WRONG:

    venue       ACM Trans / In Proceedings / pp. 12-34 / vol. / doi:
                Conservative and precise, but misses a bare title whose venue wrapped
                onto the next line and so became a different "sentence" -- which is most
                reference entries. Alone it found only 54 bibliography-only papers.
    title       a verbatim anchor title, but only when it COVERS >=30% of the sentence.
                Flagging any sentence containing the title was wrong: it demoted papers
                whose own front matter or prose quotes it. Coverage separates
                "Halide: a language and compiler for..." (a reference, 41%) from a
                paragraph that mentions the title in passing (7-10%).
    numbered    the sentence opens with a citation marker, `[16] ...`
    authors     an author list: two or more `Surname, X.` or `First Last,` runs, or
                `... & Amarasinghe`. This is what coverage alone missed -- a reference
                with six authors ahead of the title scores low coverage and still is a
                reference. It moved 20 papers that coverage had wrongly called `body`.

    NOT a signal: `arXiv:` on its own. It appears in the page-margin stamp of every arXiv
    preprint ("arXiv:1610.09405v1 [cs.SE] 28 Oct 2016"), which lands inside body sentences
    and flagged them as evidence-free.

The 0.30 coverage threshold is not load-bearing: 0.20 gives 196 bibliography-only papers
and 0.35 gives 173, so nothing hinges on the exact value.

A hit that appears in the paper's own front matter (`abstract_like`) is never a reference
-- a paper whose OWN title carries an anchor title is a Halide paper, not a citer. On this
corpus the guard changes no verdict, because those papers all have other body hits; it is
kept so the case cannot misfire later.

Known imprecision, stated rather than hidden: sentence splitting sometimes glues a body
sentence to the reference that follows it. The paper-level rule tolerates it, because a
paper is only called citation-only when EVERY one of its hits is a reference line, which
fails safe toward under-flagging.

    python3 curate/fulltext_evidence.py --out data/pools/fulltext_evidence.json
"""
import argparse
import json
import re

VENUE = re.compile(
    r"ACM Trans|IEEE Trans|In Proc|Proceedings of|pp\.\s*\d|doi:|SIGPLAN Not|vol\.\s*\d",
    re.I,
)
# The anchor papers' own titles, as they appear inside a reference entry.
TITLE = re.compile(
    r"language and compiler for optimizing parallelism"
    r"|automatically scheduling halide"
    r"|learning to optimize halide"
    r"|differentiable programming for image processing"
    r"|halide.{0,3}s scheduling language",
    re.I,
)
NUMBERED = re.compile(r"^\s*\[\d{1,3}\]")
AUTHORS = re.compile(
    r"([A-Z][a-zA-Z'`\u00b4^-]+,\s*[A-Z]\.){2,}"          # Adams, A., Ma, K.,
    r"|([A-Z][a-z]+\s+[A-Z][a-zA-Z\u00a8\u00b4`^-]+,\s*){2,}"  # Andrew Adams, Karima Ma,
    r"|\s&\s[A-Z][a-z]+"                                   # ... & Amarasinghe
)
COVERAGE = 0.30


def title_coverage(sentence):
    m = TITLE.search(sentence)
    return len(m.group(0)) / max(len(sentence), 1) if m else 0.0


def is_reference(sentence, front_matter=""):
    s = sentence.strip()
    if not s:
        return False
    # The paper's own title block is not a citation of someone else.
    if front_matter and s[:60] in front_matter:
        return False
    return bool(
        VENUE.search(s)
        or NUMBERED.search(s)
        or AUTHORS.search(s)
        or title_coverage(s) >= COVERAGE
    )


def classify(hits, front_matter=""):
    if not hits:
        return "none"
    if all(is_reference(s, front_matter) for s in hits):
        return "bibliography"
    return "body"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fulltext", default="data/pools/fulltext_state.json")
    ap.add_argument("--out")
    args = ap.parse_args()

    with open(args.fulltext) as f:
        papers = json.load(f)

    verdicts, tally = {}, {"body": 0, "bibliography": 0, "none": 0}
    for pid, rec in papers.items():
        hits = rec.get("halide_hits") or []
        v = classify(hits, rec.get("abstract_like") or "")
        verdicts[pid] = {"verdict": v, "n_hits": len(hits)}
        tally[v] += 1

    print(f"papers: {len(papers)}")
    print(f"  body          {tally['body']:5d}   real evidence")
    print(f"  bibliography  {tally['bibliography']:5d}   every hit is a reference line")
    print(f"  none          {tally['none']:5d}   no hit at all")
    print(f"  -> citation-only (bibliography + none): "
          f"{tally['bibliography'] + tally['none']}")

    if args.out:
        with open(args.out, "w") as f:
            json.dump({
                "schema_version": 2,
                "note": "body = at least one non-reference Halide sentence. bibliography = "
                        "every hit is a reference line. none = no hit. The last two are the "
                        "citation-only population and the judged pass should read this "
                        "verdict rather than the raw hit count.",
                "counts": tally,
                "papers": verdicts,
            }, f, indent=1)
        print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
