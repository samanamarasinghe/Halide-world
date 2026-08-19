"""Normalise raw affiliation strings to a parent institution.

His ruling of 2026-08-19: **MIT CSAIL and MIT LIDS are both Massachusetts
Institute of Technology.** A lab, department, centre or institute inside a
university rolls up to the university. The index answers "where were they", and
CSAIL is not somewhere anyone is employed.

The space, measured before choosing a method: 5,446 affiliation strings, 1,673
distinct. MIT alone appears in 37 spellings, one of them misspelt
("Massachusettes Institute of Technology CSAIL"). The head is NOT enough to
hand-alias -- the top 100 distinct strings cover only 34% of occurrences and the
top 800 cover 82% -- so this is rules first, with an explicit table only where
rules cannot reach.

THE RULES, in order:

1. SPLIT ON COMMAS and drop geography. Country, US state, city, postcode and
   street segments carry no institution and are most of what makes 37 spellings
   of one university.
2. DROP SUB-UNIT SEGMENTS -- Department of X, School of Y, Faculty, Laboratory,
   Centre, Division, Group, College of. This is his ruling at segment level: the
   university survives, its parts do not.
3. Of what remains, prefer the segment that NAMES an organisation, else take the
   last remaining segment.
4. Only then consult ALIASES, and only as an explicit table.

WHY NO ACRONYM EXPANSION: it was tried on this corpus and rejected, because it
turned ARM into the American Rock Mechanics Association and MIT into the Moscow
Institute of Thermal Technology. `ARM` here maps to Arm because the table says
so, not because a rule inferred it. 175 distinct strings (522 occurrences, ~10%)
begin with a bare acronym and name no university at all; those are what the
table is for, and anything the table does not know stays UNRESOLVED rather than
being guessed.

Unresolved is a real, counted outcome (453 of 5,446). A wrong institution is
invisible once written; an unresolved one is visible and fixable.

RESULT: 5,446 strings, 1,673 distinct -> 605 institutions, 91% resolved.

THREE BUGS THIS PASS PRODUCED, each worth remembering:
  * `\\b(universit|institut)\\b` MATCHES NOTHING -- a trailing word boundary
    after a PREFIX can never fire, because "university" continues with a word
    character. It sent Stanford, Tsinghua and Edinburgh to `unresolved` and
    resolution read 34% instead of 91%. A regex matching nothing looks exactly
    like a signal that is absent.
  * Splitting on " and " whenever both halves looked organisational tore
    "University of Science and Technology of China" in half and made a bare
    "Technology" the 11th most common institution. Both halves must resolve to a
    KNOWN institution first.
  * Fixing the UC over-merge traded it for an under-merge: Berkeley split three
    ways across "at Berkeley", ", Berkeley" and ", Berkeley, Berkeley".
    `tidy_campus` is what keeps both directions honest.

    python3 curate/normalize_affiliations.py --out data/pools/affiliations_normalized.json
"""
import argparse, collections, json, re, sys

sys.stdout.reconfigure(line_buffering=True)

# --- 1. geography ----------------------------------------------------------
COUNTRIES = {
    "usa", "us", "u.s.a.", "united states", "united states of america", "uk",
    "united kingdom", "england", "scotland", "china", "p.r. china", "pr china",
    "germany", "france", "japan", "korea", "south korea", "republic of korea",
    "india", "canada", "switzerland", "netherlands", "the netherlands", "spain",
    "italy", "sweden", "belgium", "israel", "australia", "singapore", "brazil",
    "russia", "poland", "austria", "denmark", "finland", "norway", "ireland",
    "portugal", "greece", "turkey", "taiwan", "hong kong", "czech republic",
    "hungary", "romania", "mexico", "chile", "argentina", "new zealand", "iran",
    "saudi arabia", "uae", "egypt", "south africa", "vietnam", "thailand",
}
US_STATES = {
    "al", "ak", "az", "ar", "ca", "co", "ct", "de", "fl", "ga", "hi", "id",
    "il", "in", "ia", "ks", "ky", "la", "me", "md", "ma", "mi", "mn", "ms",
    "mo", "mt", "ne", "nv", "nh", "nj", "nm", "ny", "nc", "nd", "oh", "ok",
    "or", "pa", "ri", "sc", "sd", "tn", "tx", "ut", "vt", "va", "wa", "wv",
    "wi", "wy", "dc",
}
POSTCODE = re.compile(r"\d{4,6}|\b\d{5}(-\d{4})?\b")
STREET = re.compile(r"\b(street|st\.|road|rd\.|ave|avenue|drive|dr\.|blvd|"
                    r"box|suite|floor|building|bldg)\b", re.I)

# --- 2. sub-units ----------------------------------------------------------
# His ruling: these roll up. A segment that is only a sub-unit is dropped.
SUBUNIT = re.compile(
    r"^\s*(the\s+)?("
    r"dept\.?|department|school|faculty|division|college of|graduate school|"
    r"laborator(y|ies)|lab\.?|centre|center|institute for|institute of|"
    r"research (group|center|centre|lab|laboratory|institute)|"
    r"group|chair|section|program|programme|unit|team|academy of"
    r")\b", re.I)

# a sub-unit ACRONYM that stands for a part of a named parent
SUBUNIT_ACRONYM = {
    "csail": "Massachusetts Institute of Technology",
    "lids": "Massachusetts Institute of Technology",
    "eecs": None,          # ambiguous on its own -- needs a parent in the string
    "cse": None,
    "media lab": "Massachusetts Institute of Technology",
}

# NOTE the \w* suffixes. Written as `\b(universit|institut|...)\b` this regex
# matches NOTHING -- see the docstring.
ORG_WORD = re.compile(
    r"\b(universit\w*|institut\w*|college|academy|polytechnic|school of|"
    r"inc\.?|ltd\.?|llc|corp\w*|gmbh|labs?\b|laborator\w*|"
    r"research|technolog\w*|hochschule|universidad|universita|universite|"
    r"academia|akadem\w*)", re.I)

# --- 4. explicit aliases. NOT expansions -- a table, deliberately -----------
ALIASES = {
    "mit": "Massachusetts Institute of Technology",
    "mit csail": "Massachusetts Institute of Technology",
    "mit lids": "Massachusetts Institute of Technology",
    "massachusetts institute of technology": "Massachusetts Institute of Technology",
    "massachusettes institute of technology": "Massachusetts Institute of Technology",
    "eth": "ETH Zurich", "eth zurich": "ETH Zurich", "eth zürich": "ETH Zurich",
    "epfl": "EPFL",
    "uc berkeley": "University of California, Berkeley",
    "university of california berkeley": "University of California, Berkeley",
    "uc davis": "University of California, Davis",
    "ucla": "University of California, Los Angeles",
    "ucsd": "University of California, San Diego",
    "cmu": "Carnegie Mellon University",
    "carnegie mellon university": "Carnegie Mellon University",
    "kaist": "KAIST", "kth": "KTH Royal Institute of Technology",
    "tu dresden": "TU Dresden", "tu delft": "Delft University of Technology",
    "tu munich": "Technical University of Munich",
    "technische universität münchen": "Technical University of Munich",
    "nvidia": "NVIDIA", "amd": "AMD", "arm": "Arm", "intel": "Intel",
    "ibm": "IBM", "google": "Google", "google research": "Google",
    "google deepmind": "Google", "microsoft": "Microsoft",
    "microsoft research": "Microsoft", "meta": "Meta", "facebook": "Meta",
    "apple": "Apple", "qualcomm": "Qualcomm", "huawei": "Huawei",
    "alibaba": "Alibaba", "tencent": "Tencent", "samsung": "Samsung",
    "adobe": "Adobe", "adobe research": "Adobe", "inria": "Inria",
    "cnrs": "CNRS", "cea": "CEA", "mpi": None,
    "ict": None, "cas": None,   # ambiguous alone; a parent must appear
}


def strip_geo(seg):
    s = seg.strip().strip(".")
    low = s.lower().strip()
    if not low:
        return None
    if low in COUNTRIES or low in US_STATES:
        return None
    if POSTCODE.search(s) and not ORG_WORD.search(s):
        return None
    if STREET.search(s) and not ORG_WORD.search(s):
        return None
    return s


# Multi-campus systems where the campus IS the institution. Collapsing
# "University of California, Berkeley" to "University of California" merges
# Berkeley, Davis, San Diego and Los Angeles into one node -- a real loss, and
# the comma split is what causes it.
CAMPUS_SYSTEM = re.compile(
    r"^(university of california|university of texas|university of illinois|"
    r"university of wisconsin|state university of new york|"
    r"universit(y|e) of colorado|university of michigan)\b", re.I)

CAMPUS_TIDY = re.compile(r"\s+at\s+", re.I)


def tidy_campus(name):
    """`University of California at Berkeley, Berkeley` and `..., Berkeley` are
    one institution. Without this the campus fix trades an over-merge for an
    under-merge and Berkeley splits three ways."""
    n = CAMPUS_TIDY.sub(", ", name.strip())
    n = re.sub(r"\s*&amp;?\s*$", "", n)
    n = re.sub(r"[-\s]+", " ", n).strip(" ,")
    parts = [p.strip() for p in n.split(",") if p.strip()]
    out = []
    for p in parts:
        if out and p.lower() == out[-1].lower():
            continue                     # `, Berkeley, Berkeley`
        if out and p.lower() in out[0].lower():
            continue                     # campus already inside the head
        out.append(p)
    return ", ".join(out[:2])


def with_campus(segs, idx):
    """`University of California` + `Berkeley` -> `University of California, Berkeley`."""
    head = segs[idx]
    if not CAMPUS_SYSTEM.match(head.strip()):
        return head
    for nxt in segs[idx + 1:idx + 2]:
        n = nxt.strip()
        if n and not ORG_WORD.search(n) and len(n.split()) <= 3:
            return tidy_campus(f"{head.strip()}, {n}")
    return tidy_campus(head)


def canonical(raw):
    """Return (institution, or a list of them for a dual affiliation, or None)."""
    if not raw or not raw.strip():
        return None, "empty"
    low = raw.lower().strip().strip(".")

    # whole-string alias first -- catches `MIT CSAIL`, `ETH Zurich, Switzerland`
    head = re.split(r"[,;]", low)[0].strip()
    if head in ALIASES and ALIASES[head]:
        return ALIASES[head], "alias"

    # A dual affiliation ("Adobe and MIT CSAIL") is TWO institutions, and taking
    # the first silently deletes the other -- the same class of invisible loss as
    # a wrong merge. BOTH halves must resolve to a KNOWN institution before
    # splitting; a looser test tears real names apart (see the docstring). This
    # must run BEFORE the sub-unit scan, or `csail` matches and the Adobe half
    # is lost.
    if re.search(r"\s+and\s+", raw, re.I):
        parts = re.split(r"\s+and\s+", raw, flags=re.I)
        if len(parts) == 2:
            resolved = [canonical(p) for p in parts]
            if all(r[1] in ("alias", "alias_within", "subunit_acronym")
                   for r in resolved):
                out = []
                for inst, _ in resolved:
                    out.extend(inst if isinstance(inst, list) else [inst])
                if len(set(out)) == 2:
                    return sorted(set(out)), "dual_affiliation"

    for k in SUBUNIT_ACRONYM:
        if re.search(rf"\b{re.escape(k)}\b", low) and SUBUNIT_ACRONYM[k]:
            return SUBUNIT_ACRONYM[k], "subunit_acronym"

    segs = [strip_geo(s) for s in re.split(r"[,;]", raw)]
    segs = [s for s in segs if s]
    kept = [s for s in segs if not SUBUNIT.search(s)]
    pool = kept or segs
    if not pool:
        return None, "geography_only"

    named = [i for i, s in enumerate(pool) if ORG_WORD.search(s)]
    pick = (with_campus(pool, named[0]) if named else pool[-1]).strip()

    p = pick.lower().strip().strip(".")
    p = re.sub(r"\s*\(.*?\)\s*", " ", p).strip()
    if p in ALIASES:
        return (ALIASES[p], "alias") if ALIASES[p] else (None, "ambiguous_alias")
    for key, val in ALIASES.items():
        if val and re.search(rf"\b{re.escape(key)}\b", p):
            return val, "alias_within"
    if ORG_WORD.search(pick):
        out = tidy_campus(pick) if CAMPUS_SYSTEM.match(pick) else pick
        return out if any(c.isupper() for c in out) else out.title(), "as_written"
    return None, "unresolved"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--affiliations", default="data/pools/affiliations_state.json")
    ap.add_argument("--out", default="data/pools/affiliations_normalized.json")
    args = ap.parse_args()

    src = json.load(open(args.affiliations))
    raw = collections.Counter()
    for v in src.values():
        for a in (v.get("authors") or []):
            for s in (a.get("affiliations") or []):
                raw[s.strip()] += 1

    mapping, why = {}, collections.Counter()
    for s in raw:
        inst, reason = canonical(s)
        mapping[s] = inst if isinstance(inst, list) or inst is None else [inst]
        why[reason] += raw[s]

    total = sum(raw.values())
    resolved = sum(raw[s] for s, v in mapping.items() if v)
    canon = collections.Counter()
    for s, n in raw.items():
        for inst in (mapping[s] or []):
            canon[inst] += n
    print(f"{total} strings, {len(raw)} distinct -> {len(canon)} institutions")
    print(f"resolved {resolved}/{total} = {100*resolved//total}%")
    print("\nby route: " + ", ".join(f"{k} {v}" for k, v in why.most_common()))
    print("\ntop institutions after rollup:")
    for i, n in canon.most_common(15):
        print(f"   {n:4d}  {i[:70]}")

    json.dump({"schema_version": 1,
               "note": ("Raw affiliation string -> parent institution. His "
                        "ruling: a lab, department or centre rolls up to its "
                        "university (MIT CSAIL and MIT LIDS are both MIT). "
                        "A list means a dual affiliation. null means UNRESOLVED "
                        "and is deliberate -- a wrong institution is invisible "
                        "once written, an unresolved one is visible and fixable."),
               "n_strings": total, "n_distinct": len(raw),
               "n_institutions": len(canon), "n_resolved": resolved,
               "institutions": dict(canon.most_common()),
               "map": mapping},
              open(args.out, "w"), indent=1)
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
