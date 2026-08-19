"""Rules pass — apply the tier cuts, then judge the tail by rule.

Saman's rulings of 2026-08-19:
  paper cut 4, repo cut 3, citation weighting unchanged,
  Buck / tinygrad / MNN added back by hand as canonicals,
  `packaging` is its OWN role value (not `uses`, not `drop`),
  and the residual tail KEEPS `uses` at importance 1 rather than dropping.

The design rule here is that a rule FIRES ONLY WHEN CONFIDENT. Anything else
escalates. Coverage is therefore the number to watch: if the rules cover little
of the tail, the judged pass swallows the saving and the tier split bought
nothing.

`escalate = head OR evidence=poor OR no rule fired`, per the earlier ruling that
low-evidence records escalate regardless of tier.

    python3 curate/rules_pass.py --paper-cut 4 --repo-cut 3
"""
import argparse, json, os, re, sys, collections

sys.stdout.reconfigure(line_buffering=True)

# --- the three canonicals Saman asked to add back --------------------------
# These dropped out entirely because the cleanup pass crowns a canonical only
# from inside the candidate set, and none of these was ever harvested as a
# Halide candidate -- their relationship to Halide is real but shallow, so no
# Halide-shaped search surfaced them. Roles are stated, not inferred: each is
# the upstream whose file the copies were carrying.
MANUAL_CANONICALS = [
    {"repo": "facebook/buck2", "role": "uses",
     "reason": "ships a `halide_library` build rule (prelude/decls/halide_rules.bzl); "
               "11 repos in the index were carrying copies of it"},
    {"repo": "facebook/buck", "role": "uses",
     "reason": "the Buck v1 lineage of the same `halide_library` rule "
               "(docs/rule/halide_library.soy)"},
    {"repo": "tinygrad/tinygrad", "role": "uses",
     "reason": "extra/gemm/halide_gemm.py; 11 repos carried copies, most via openpilot"},
    {"repo": "alibaba/MNN", "role": "uses",
     "reason": "vendors Halide's runtime header (HalideRuntime.h); 11 repos "
               "carried copies of it"},
]

# --- repo rules ------------------------------------------------------------
USES_PHRASE = re.compile(
    r"(built|based|implemented|written|powered)\s+(on|with|in|using|by)\s+halide"
    r"|halide[- ](based|backend|pipeline|implementation|port|binding|wrapper)"
    r"|uses?\s+halide|using\s+the\s+halide", re.I)

# Anything claiming to fork, patch, modify or COPY Halide escalates. "copy" and
# the informal "mods" belong here: `Copy of Tyler's Distributed Halide work, but
# with mods for tiramisu comparison` was ruled `uses` by the README rule when it
# is plainly a copy or an extension. `extends` and `drop` are both too expensive
# to assign by regex, so a self-declared copy goes to the judged pass. Adding
# this caught three: jrayzero/TylerDistHalide, gchauras/Halide ("Halide fork"),
# fl4p/HalideAndroidCamera2Example ("A fork from Halide app HelloAndroidCamera2").
EXTENDS_PHRASE = re.compile(
    r"(fork|extension|extends?|patch(ed)?|modif(y|ies|ied)|mod(s|ded)?|copy|copied|clone)"
    r"\b[^.]{0,40}\bhalide"
    r"|\bhalide\b[^.]{0,40}\b(fork|copy|clone|with mods?|modified|patched)\b"
    r"|adds?\s+.{0,40}\s+to\s+halide|halide\s+(backend|frontend)\s+for", re.I)
HALIDE_NAMED = re.compile(r"^halide([-_.].*)?$", re.I)


def repo_rule(r, meta):
    """Return (role, importance, rule) or None to escalate."""
    raw = meta.get(r["repo"], {}) or {}
    text = " ".join(filter(None, [raw.get("description"), (raw.get("readme") or "")[:4000]]))

    if r["status"] == "packaging":
        return "packaging", 1, "distribution package tree (his ruling: own role value)"
    if r.get("role_source") == "fork_diff":
        return r["role"], 3, "commit diff against upstream already ruled"

    # A repo NAMED Halide is a copy or a fork and the signatures cannot tell
    # which. Never guessed -- this is what the commit diff exists for.
    if HALIDE_NAMED.match(r["repo"].split("/")[-1]):
        return None
    if "likely_unmodified_copy_reuploaded" in r["flags"]:
        return None

    if EXTENDS_PHRASE.search(text):
        return None          # `extends` is too costly to assign by regex
    if USES_PHRASE.search(text):
        return "uses", 2, "description or README states it builds on Halide"

    # The residual tail: a handful of signature matches, low stakes, and nothing
    # in the project's own words about Halide. Given that ~81% of repo
    # references in this corpus are incidental, `uses` at importance 1 is the
    # honest reading -- it did link Halide, and it is not a Halide project.
    # HIS RULING 2026-08-19: keep `uses`/1 here rather than dropping. Importance
    # 1 already says "barely", and a dropped node cannot be audited.
    if not r["flags"] or "evidence_is_halides_own_tree" not in r["flags"]:
        if (r.get("n_matches") or 0) <= 20 and text:
            return "uses", 1, "incidental Halide reference, no Halide claim in its own words"
    return None


# --- paper rules -----------------------------------------------------------
HALIDE_TITLE = re.compile(r"\bhalide\b", re.I)

# The CITING SENTENCE is the best evidence there is, and the compact pool throws
# it away -- lane_a.json keeps it. 384 of the 479 papers no rule could reach have
# one. Reading it turns "S2 gave no intent label" into a decidable record.
CTX_USES = re.compile(
    r"\b(we|our|this (work|paper)|is|are|was|were)\b[^.]{0,60}\b(use[sd]?|implement(ed)?|"
    r"built|build|written|writing|based|develop(ed)?|port(ed)?|express(ed)?)\b[^.]{0,60}\bhalide\b"
    r"|\bhalide\b[^.]{0,40}\b(is used|was used|we use|to implement|to express)\b", re.I)
CTX_MENTION = re.compile(
    r"\b(such as|like|e\.g\.|for example|including|among (them|others)|"
    r"prior work|previous work|similar(ly)? to|compared (to|with)|inspired by)\b"
    r"[^.]{0,80}\bhalide\b", re.I)
CTX_EXTENDS = re.compile(
    r"\b(extend|extends|extended|modif(y|ies|ied)|patch(es|ed)?|fork(s|ed)?|"
    r"add(s|ed)? .{0,30} to)\b[^.]{0,40}\bhalide\b", re.I)


def context_rule(contexts):
    """Judge from the citing sentences. Precedence matters: an `extends` claim
    always escalates, a `uses` claim beats a mere mention, and a sentence that
    only lists Halide among examples is `writes-about`.

    CTX_USES fires rarely (4 records) and that is expected, not a bug: most
    citing sentences describe the CITED work rather than the citing one. The
    value of pulling the sentences in is that the judged pass can now read them.
    """
    blob = " ".join((c.get("text") or "") for c in contexts)[:4000]
    if not blob.strip():
        return None
    if CTX_EXTENDS.search(blob):
        return None                      # too costly to assign by regex
    if CTX_USES.search(blob):
        return "uses", 2, "citing sentence states the work uses Halide"
    if CTX_MENTION.search(blob):
        return "writes-about", 1, "citing sentence lists Halide among examples"
    return None


def paper_rule(p, work, enriched, contexts=()):
    text = " ".join(filter(None, [work.get("title"), enriched.get("abstract")]))
    intents = set(work.get("intents") or [])

    # A paper naming Halide in its title is never decided by rule.
    if HALIDE_TITLE.search(work.get("title") or ""):
        return None
    if work.get("key_on"):
        return None          # influential on an anchor: too costly to guess

    if "methodology" in intents:
        return "uses", 2, "S2 marks the Halide citation as methodological"
    if intents and intents <= {"background"} and (work.get("n_contexts") or 0) >= 1:
        return "writes-about", 1, "cites Halide as background only"
    return context_rule(contexts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tiers", default="data/pools/tiers.json")
    ap.add_argument("--papers", default="data/pools/lane_a_compact.json")
    ap.add_argument("--full", default="data/pools/lane_a.json",
                    help="carries the citing sentences the compact pool drops")
    ap.add_argument("--enriched", default="data/pools/doi_enriched_state.json")
    ap.add_argument("--repos", default="data/pools/lane_b_curatable.json")
    ap.add_argument("--repometa", default="data/pools/repo_meta_state.json")
    ap.add_argument("--paper-cut", type=float, default=4)
    ap.add_argument("--repo-cut", type=float, default=3)
    ap.add_argument("--out", default="data/pools/rules_pass.json")
    args = ap.parse_args()

    tiers = json.load(open(args.tiers))
    enriched = json.load(open(args.enriched))
    meta = json.load(open(args.repometa))
    works = {(w.get("s2_id") or w.get("doi")): w
             for w in json.load(open(args.papers))["works"]}
    full = json.load(open(args.full))["works"] if os.path.exists(args.full) else {}
    repos = {r["repo"]: r for r in json.load(open(args.repos))["repos"]}

    out = {"papers": [], "repos": []}
    stats = collections.Counter()

    for row in tiers["papers"]:
        head = row["stakes"] >= args.paper_cut
        rec = dict(row, tier="head" if head else "tail")
        w = works.get(row["id"]) or {"title": row["title"]}
        e = enriched.get((w.get("doi") or (row["id"][3:] if row["id"].startswith("oc:") else "")), {}) or {}
        if head or row["evidence"] == "poor":
            rec["escalate"], rec["why"] = True, "head" if head else "evidence poor"
        else:
            hit = paper_rule(row, w, e, (full.get(row["id"]) or {}).get("contexts") or [])
            if hit:
                rec["role"], rec["importance"], rec["rule"] = hit
                rec["escalate"] = False
            else:
                rec["escalate"], rec["why"] = True, "no rule fired"
        stats[("paper", "escalate" if rec["escalate"] else rec.get("role"))] += 1
        out["papers"].append(rec)

    for row in tiers["repos"]:
        head = row["stakes"] >= args.repo_cut
        rec = dict(row, tier="head" if head else "tail")
        r = repos.get(row["id"])
        if head or row["evidence"] == "poor":
            rec["escalate"], rec["why"] = True, "head" if head else "evidence poor"
        else:
            hit = repo_rule(r, meta) if r else None
            if hit:
                rec["role"], rec["importance"], rec["rule"] = hit
                rec["escalate"] = False
            else:
                rec["escalate"], rec["why"] = True, "no rule fired"
        stats[("repo", "escalate" if rec["escalate"] else rec.get("role"))] += 1
        out["repos"].append(rec)

    # the packaging repos and the manual canonicals are decided outright
    for r in repos.values():
        if r["status"] == "packaging":
            out["repos"].append({"id": r["repo"], "kind": "repo", "tier": "tail",
                                 "role": "packaging", "importance": 1,
                                 "escalate": False,
                                 "rule": "distribution package tree (his ruling: own role value)"})
            stats[("repo", "packaging")] += 1
    for m in MANUAL_CANONICALS:
        out["repos"].append(dict(m, kind="repo", tier="head", importance=2,
                                 escalate=False, added_by_hand=True,
                                 rule="canonical added by hand on his ruling"))
        stats[("repo", "manual")] += 1

    for kind in ("paper", "repo"):
        rows = out[kind + "s"]
        n = len(rows)
        esc = sum(1 for r in rows if r["escalate"])
        print(f"\n=== {kind.upper()}S: {n} records ===")
        print(f"  decided by rule : {n-esc}  ({100*(n-esc)//n}%)")
        print(f"  escalated       : {esc}")
        for (k, v), c in sorted(stats.items()):
            if k == kind:
                print(f"    {str(v):<14} {c}")
        why = collections.Counter(r.get("why") for r in rows if r["escalate"])
        print("  escalation reasons: " + ", ".join(f"{k} {v}" for k, v in why.most_common()))

    json.dump({"schema_version": 1, "paper_cut": args.paper_cut,
               "repo_cut": args.repo_cut, **out}, open(args.out, "w"), indent=1)
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
