"""Pre-pass — resolve the citation-only papers by rule, before any judging.

His ruling of 2026-08-19: pre-pass first, then route the remainder by evidence
type. The pre-pass exists to shrink the judged queue with a rule he has seen,
rather than spending judgement on records whose answer is already determined.

THE RULE FIRES ON `bibliography` ONLY, NOT ON `none`, and that is a deliberate
narrowing of what was proposed.

  bibliography  the full text mentions Halide and EVERY mention is a reference
                line. That is POSITIVE evidence: we read the paper, we found the
                mention, and it is a citation. -> `writes-about`, importance 1.

  none          no mention found anywhere in the extracted text. That is the
                ABSENCE of evidence, not evidence of absence, and the numbers
                say so: the `none` group has a median of 22 pages against 14 for
                the other two, and **26 of its 61 papers are longer than the
                40-page cap `extract_pdf_text.py` reads**. For those we did not
                read the document, we read the front of it. They ESCALATE.

A paper wrongly filed `writes-about` is invisible afterwards -- it looks like a
finished record. A paper wrongly escalated only costs a judging slot. So the
rule takes the side that fails visibly.

Ten `bibliography` verdicts were sampled by hand before this was written: all
ten were unambiguous reference lines ("Halide: a language and compiler for
optimizing parallelism...", "Learning to Optimize Halide with Tree Search").
No body discussion appeared in any of them, and none of the 61 `none` papers
shows a hyphen-broken "Hal-ide" that the extractor could have missed.

MEASURED RESULT: of 1,158 escalating papers, 105 resolve here and the queue
becomes 1,053. The other 92 bibliography-only papers in the corpus were already
decided by the rules pass and never reached this queue.

TWO THINGS THIS PASS SURFACES THAT IT CANNOT FIX:
  * 13 of the escalating `none` papers are over the page cap. Raising it in
    `extract_pdf_text.py` would resolve them properly. That is his run, on his
    disk.
  * 590 of the 1,053 remaining have NO FULL TEXT AT ALL -- 440 S2 papers whose
    PDF was never fetched, and 150 OpenCitations-only records with no `s2_id` to
    match a PDF filename. That is the single biggest constraint on the judged
    pass, and it is a fetching problem rather than a judging one.

    python3 curate/prepass.py --out data/pools/prepass.json
"""
import argparse, collections, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(line_buffering=True)

PAGE_CAP = 40          # must match extract_pdf_text.py


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rules", default="data/pools/rules_pass.json")
    ap.add_argument("--fulltext", default="data/pools/fulltext_state.json")
    ap.add_argument("--out", default="data/pools/prepass.json")
    args = ap.parse_args()

    from fulltext_evidence import classify

    ft = json.load(open(args.fulltext))
    rules = json.load(open(args.rules))

    resolved, escalate = [], []
    stats = collections.Counter()
    for row in rules["papers"]:
        if not row.get("escalate"):
            continue
        stats["escalating_before"] += 1
        rec = ft.get(row["id"])
        if not rec or rec.get("error"):
            stats["no_fulltext"] += 1
            escalate.append({**row, "prepass": "no full text"})
            continue
        hits = rec.get("halide_hits") or []
        verdict = "none" if not hits else classify(hits)

        if verdict == "bibliography":
            resolved.append({"id": row["id"], "title": row.get("title"),
                             "role": "writes-about", "importance": 1,
                             "rule": "full text mentions Halide only in the "
                                     "bibliography",
                             "n_hits": len(hits),
                             "evidence": hits[:2]})
            stats["resolved_bibliography"] += 1
        elif verdict == "none":
            over = (rec.get("n_pages") or 0) > PAGE_CAP
            escalate.append({**row, "prepass": "no mention found",
                             "over_page_cap": over,
                             "n_pages": rec.get("n_pages")})
            stats["escalate_none_over_cap" if over
                  else "escalate_none_within_cap"] += 1
        else:
            escalate.append({**row, "prepass": "body evidence",
                             "n_hits": len(hits)})
            stats["escalate_body"] += 1

    print(f"escalating papers before the pre-pass : {stats['escalating_before']}")
    print(f"  RESOLVED as writes-about (bibliography only): {stats['resolved_bibliography']}")
    print(f"  still escalating, body evidence      : {stats['escalate_body']}")
    print(f"  still escalating, no mention (within cap): {stats['escalate_none_within_cap']}")
    print(f"  still escalating, no mention (OVER the {PAGE_CAP}-page cap): "
          f"{stats['escalate_none_over_cap']}")
    print(f"  still escalating, no full text at all: {stats['no_fulltext']}")
    print(f"\njudged queue: {stats['escalating_before']} -> {len(escalate)}")

    json.dump({"schema_version": 1,
               "note": ("Pre-pass. `bibliography` is POSITIVE evidence that the "
                        "only mention is a citation, so it resolves to "
                        "writes-about. `none` is the ABSENCE of evidence and "
                        "escalates -- some of those papers are longer than the "
                        "40-page extraction cap, so the document was not fully "
                        "read. A wrong writes-about is invisible; a wrong "
                        "escalation only costs a judging slot."),
               "counts": dict(stats),
               "n_resolved": len(resolved), "n_escalating": len(escalate),
               "resolved": resolved, "escalating": escalate},
              open(args.out, "w"), indent=1)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
