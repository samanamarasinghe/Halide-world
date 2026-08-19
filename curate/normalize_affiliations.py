"""Normalise raw affiliation strings to a parent institution.

His ruling of 2026-08-19: **MIT CSAIL and MIT LIDS are both Massachusetts
Institute of Technology.** A lab, department, centre or institute inside a
university rolls up to the university. The index answers "where were they", and
CSAIL is not somewhere anyone is employed.

The space, measured before choosing a method: 5,446 affiliation strings, 1,673
distinct. MIT alone appears in 37 spellings, one of them misspelt
("Massachusettes Institute of Technology CSAIL"). The head is NOT enough to
hand-alias -- the top 100 distinct strings cover only 34% of occurrences -- so
this is rules first, with an explicit table only where rules cannot reach.

THE RULES, in order: split on commas and drop geography; drop sub-unit segments
(Department, School, Laboratory, Centre, Institute-of, State Key Lab); prefer the
segment naming an organisation; only then consult ALIASES.

WHY NO ACRONYM EXPANSION: tried on this corpus and rejected, because it turned
ARM into the American Rock Mechanics Association and MIT into the Moscow
Institute of Thermal Technology. `ARM` maps to Arm because the table says so.
Anything the table does not know stays UNRESOLVED rather than guessed --
unresolved is a counted outcome (~10%), because a wrong institution is invisible
once written and an unresolved one is visible and fixable.

RESULT: 5,446 strings, 1,673 distinct -> 559 institutions, 90% resolved.

FIVE BUGS THIS PASS PRODUCED, each worth remembering:
  * `\\b(universit|institut)\\b` MATCHES NOTHING -- a trailing word boundary after
    a PREFIX can never fire. It sent Stanford, Tsinghua and Edinburgh to
    `unresolved` and resolution read 34% instead of 91%. A regex matching nothing
    looks exactly like a signal that is absent.
  * Splitting on " and " whenever both halves looked organisational tore
    "University of Science and Technology of China" in half and made a bare
    "Technology" the 11th most common institution.
  * Fixing the UC over-merge traded it for an under-merge: Berkeley split three
    ways across "at Berkeley", ", Berkeley" and ", Berkeley, Berkeley".
  * Crossref deposits carry raw HTML ENTITIES. `University of M&#x00FC` and
    `Peking University &amp` were separate institutions until `unescape` ran.
  * A bare legal suffix is not an institution -- `Inc` reached the index as one.

The detector for all of the last three: A PERSON APPEARING TO MOVE BETWEEN TWO
SPELLINGS OF ONE PLACE. Spot-checking careers that are publicly known is the
cheapest test this lane has, and it also catches genuine publisher errors --
see `data/pools/affiliation_corrections.json`.

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
    r"group|chair|section|program|programme|unit|team|academy of|"
    r"state key lab\w*|joint (software )?institute|.*joint software institute|"
    r"key laborator\w*|national (engineering|key) "
    r")\b", re.I)

# a sub-unit ACRONYM that stands for a part of a named parent
SUBUNIT_ACRONYM = {
    "csail": "Massachusetts Institute of Technology",
    "lids": "Massachusetts Institute of Technology",
    "eecs": None,          # ambiguous on its own -- needs a parent in the string
    "cse": None,
    "media lab": "Massachusetts Institute of Technology",
}

# NOTE the \w* suffixes -- see the docstring. Written with a trailing \b after a
# prefix this regex matches nothing at all.
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


# Crossref deposits carry raw HTML entities. Left undecoded they mint fake
# institutions -- `University of M&#x00FC` and `Peking University &amp` both
# appeared as separate institutions, and a person holding both spellings reads
# as having moved.
def unescape(s):
    import html
    s = html.unescape(html.unescape(s))
    return re.sub(r"&[#\w]{1,8};?", " ", s)


# German/Nordic transliterations of the same university.
TRANSLIT = {"muenster": "münster", "koeln": "köln", "zuerich": "zürich",
            "goettingen": "göttingen", "muenchen": "münchen",
            "duesseldorf": "düsseldorf", "wuerzburg": "würzburg"}

# A segment that is only a legal suffix or a stray fragment is not an
# institution. `Inc` reached the index as an institution on its own.
FRAGMENT = re.compile(r"^(inc|ltd|llc|corp|gmbh|co|plc|ag|sa|bv|the|and|"
                      r"usa|research|labs?|group)\.?$", re.I)


def strip_geo(seg):
    s = seg.strip().strip(".")
    low = s.lower().strip()
    if not low:
        return None
    if low in COUNTRIES or low in US_STATES:
        return None
    if FRAGMENT.match(low):
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

# Campus names appear with and without the comma. Left alone, "University of
# California San Diego" and "University of California, San Diego" are two
# institutions and one person looks like they moved between them.
CAMPUS_NAMES = ("berkeley", "davis", "irvine", "los angeles", "san diego",
                "santa barbara", "santa cruz", "riverside", "merced",
                "san francisco", "austin", "dallas", "el paso", "arlington",
                "urbana champaign", "chicago", "madison", "ann arbor", "boulder")

# A sub-unit that names its parent inside the SAME segment, with no comma to
# split on: "Institute of Computing Technology Chinese Academy of Sciences".
# The parent survives, per his rollup ruling. Guarded so that a university whose
# own name contains a parent -- "University of Chinese Academy of Sciences" --
# is NOT swallowed by it: that is a different institution.
PARENT_INSIDE = ("chinese academy of sciences", "russian academy of sciences",
                 "max planck", "helmholtz")


def rollup_parent(name):
    # "University of the Chinese Academy of Sciences" and "University of Chinese
    # Academy of Sciences" are one place. Done here rather than in tidy_campus,
    # which only ever runs for the multi-campus systems.
    name = re.sub(r"\buniversity of the\b", "University of", name, flags=re.I)
    low = name.lower()
    if low.startswith("university of") or low.startswith("univ"):
        return name
    for parent in PARENT_INSIDE:
        if parent in low:
            return " ".join(w.capitalize() if w not in ("of", "the") else w
                            for w in parent.split()).replace("Of", "of")
    return name


def tidy_campus(name):
    """`University of California at Berkeley, Berkeley` and `..., Berkeley` are
    one institution. Without this the campus fix trades an over-merge for an
    under-merge and Berkeley splits three ways."""
    n = CAMPUS_TIDY.sub(", ", name.strip())
    n = re.sub(r"\s*&amp;?\s*$", "", n)
    n = re.sub(r"[-\s]+", " ", n).strip(" ,")
    n = re.sub(r"\buniversity of the\b", "University of", n, flags=re.I)
    parts = [p.strip() for p in n.split(",") if p.strip()]
    # insert the missing comma before a known campus name, on the HEAD segment --
    # "University of California San Diego, La Jolla" already has a comma, so a
    # whole-string test skips it and San Diego stays split in two.
    if parts:
        for c in CAMPUS_NAMES:
            m = re.search(rf"^(.*?)\s+({re.escape(c)})$", parts[0], re.I)
            if m:
                parts = [m.group(1).strip(), m.group(2)] + parts[1:]
                break
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
    raw = unescape(raw).strip()
    low = raw.lower().strip().strip(".")
    for a, b in TRANSLIT.items():
        if a in low:
            low = low.replace(a, b)
            raw = re.sub(a, b, raw, flags=re.I)

    # whole-string alias first -- catches `MIT CSAIL`, `ETH Zurich, Switzerland`
    head = re.split(r"[,;]", low)[0].strip()
    if head in ALIASES and ALIASES[head]:
        return ALIASES[head], "alias"

    # A dual affiliation ("Adobe and MIT CSAIL") is TWO institutions, and taking
    # the first silently deletes the other. BOTH halves must resolve to a KNOWN
    # institution before splitting; a looser test tears real names apart. This
    # must run BEFORE the sub-unit scan, or `csail` matches and Adobe is lost.
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
        out = tidy_campus(pick) if CAMPUS_SYSTEM.match(pick) else rollup_parent(pick)
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

    # Final consolidation: two spellings differing only by case or accent are one
    # institution. The transliteration step above can leave `University of
    # münster` beside `University of Münster`, and a person holding both reads as
    # having moved. Keep the most frequent spelling as the canonical one.
    def fold(x):
        import unicodedata
        x = unicodedata.normalize("NFKD", x.lower())
        return re.sub(r"[^a-z0-9]", "", "".join(c for c in x if not unicodedata.combining(c)))

    best = {}
    for s_, insts in mapping.items():
        for i in (insts or []):
            k = fold(i)
            best.setdefault(k, collections.Counter())[i] += raw[s_]
    winner = {k: c.most_common(1)[0][0] for k, c in best.items()}
    for s_ in mapping:
        if mapping[s_]:
            mapping[s_] = sorted({winner[fold(i)] for i in mapping[s_]})

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
