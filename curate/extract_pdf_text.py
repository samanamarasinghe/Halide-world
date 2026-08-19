"""Full-text extraction for the papers no rule and no judge could read.

502 of the 1,158 escalating papers have NO citation context and NO abstract.
That is a data gap, not a rules problem -- a judged pass cannot read them either.
His ruling of 2026-08-19 was to extract text from the kept PDFs FIRST and then
judge everything together.

The PDFs are the ones `harvest/artifacts.py --keep-pdfs` saved to `data/pdfs/`,
named `<s2_id>.pdf`. They are gitignored and live only on his machine, which is
why this script exists as something he runs rather than something that ran here.

    pip install pypdf
    python3 curate/extract_pdf_text.py --pdf-dir data/pdfs

What it writes, per paper, into `data/pools/fulltext_state.json`:
  abstract_like  the first ~1,500 characters after the title block, which is
                 what an abstract-shaped judge prompt actually wants
  halide_hits    every sentence in the paper mentioning Halide, capped at 12.
                 This is the direct analogue of the citing sentence that turned
                 out to be the most useful evidence in the rules pass, and for
                 these papers it is the ONLY evidence there is
  n_pages, n_chars, and a reason when nothing could be read

NOTE ON COVERAGE: the 502 are 447 S2 records plus 55 OpenCitations-only records.
Only the S2 ones map to a PDF by filename -- the OC records have no s2_id, and
only 4 of them carry an open-access pdf_url. Those 51 need a separate route.

Resumable: it keeps its own state file and skips anything already done, so an
interrupted run costs nothing. Extraction is local -- no network, no rate limit.
"""
import argparse, json, os, re, sys, time

sys.stdout.reconfigure(line_buffering=True)

HALIDE = re.compile(r"\bhalide\b", re.I)
# Sentence splitting that does not break on "et al." or "Fig. 3" or "e.g."
SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\[])")
ABBREV = re.compile(r"\b(et al|e\.g|i\.e|cf|Fig|Sec|Eq|Ref|vs|approx|Dr|Prof)\.$", re.I)


def sentences(text):
    parts, buf = [], ""
    for chunk in SENT.split(text):
        buf = (buf + " " + chunk).strip() if buf else chunk
        if ABBREV.search(buf):
            continue          # the split was inside an abbreviation; keep going
        parts.append(buf)
        buf = ""
    if buf:
        parts.append(buf)
    return parts


def clean(text):
    """PDF text arrives with hyphenated line breaks and hard-wrapped lines."""
    text = text.replace("\u00ad", "")
    text = re.sub(r"-\n(?=[a-z])", "", text)      # re-join hyphenated words
    text = re.sub(r"\s*\n\s*", " ", text)
    return re.sub(r"\s{2,}", " ", text).strip()


def extract(path, max_pages=40):
    from pypdf import PdfReader
    try:
        reader = PdfReader(path)
    except Exception as e:
        return None, f"unreadable: {e.__class__.__name__}"
    if getattr(reader, "is_encrypted", False):
        try:
            reader.decrypt("")
        except Exception:
            return None, "encrypted"
    pages = reader.pages[:max_pages]
    out = []
    for p in pages:
        try:
            out.append(p.extract_text() or "")
        except Exception:
            continue
    text = clean(" ".join(out))
    if len(text) < 400:
        # A scanned paper yields almost nothing. Say so rather than recording an
        # empty success -- an empty string reads downstream as "no Halide here".
        return None, f"no extractable text ({len(text)} chars; likely scanned)"
    return {"n_pages": len(reader.pages), "n_chars": len(text),
            "abstract_like": text[:1500],
            "halide_hits": [s[:400] for s in sentences(text) if HALIDE.search(s)][:12]}, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf-dir", default="data/pdfs")
    ap.add_argument("--rules", default="data/pools/rules_pass.json")
    ap.add_argument("--out", default="data/pools/fulltext_state.json")
    ap.add_argument("--only-escalating", action="store_true", default=True,
                    help="restrict to papers the rules pass escalated (the point of the run)")
    ap.add_argument("--all", dest="only_escalating", action="store_false")
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()

    if not os.path.isdir(args.pdf_dir):
        sys.exit(f"no {args.pdf_dir}/ -- run harvest/artifacts.py --keep-pdfs first")

    wanted = None
    if args.only_escalating and os.path.exists(args.rules):
        rows = json.load(open(args.rules))["papers"]
        wanted = {r["id"] for r in rows if r.get("escalate")}
        poor = {r["id"] for r in rows if r.get("why") == "evidence poor"}
        print(f"{len(wanted)} escalating papers, of which {len(poor)} have no text at all")

    state = json.load(open(args.out)) if os.path.exists(args.out) else {}
    files = [f for f in sorted(os.listdir(args.pdf_dir)) if f.endswith(".pdf")]
    todo = [f for f in files
            if f[:-4] not in state and (wanted is None or f[:-4] in wanted)]
    if args.limit:
        todo = todo[:args.limit]
    print(f"{len(files)} PDFs on disk, {len(todo)} to read")

    t0, ok, empty = time.time(), 0, 0
    for i, f in enumerate(todo, 1):
        pid = f[:-4]
        rec, err = extract(os.path.join(args.pdf_dir, f))
        if rec:
            state[pid] = rec
            ok += 1
        else:
            state[pid] = {"error": err}
            empty += 1
        if i % 25 == 0:
            json.dump(state, open(args.out, "w"), indent=1)
            print(f"  {i}/{len(todo)}  {time.time()-t0:.0f}s  read {ok}, unreadable {empty}")
    json.dump(state, open(args.out, "w"), indent=1)

    hits = sum(1 for v in state.values() if v.get("halide_hits"))
    none = sum(1 for v in state.values()
               if not v.get("error") and not v.get("halide_hits"))
    print(f"\nwrote {args.out}: {ok} read, {empty} unreadable")
    print(f"  papers with at least one Halide sentence: {hits}")
    print(f"  read but NO Halide sentence anywhere: {none}")
    print("  -- that second number matters: a paper whose full text never says "
          "Halide is a citation-only relationship, and the judged pass should "
          "see it as such rather than as missing evidence")


if __name__ == "__main__":
    main()
