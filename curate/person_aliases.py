#!/usr/bin/env python3
"""Validate data/pools/person_aliases.json against the built person layer.

The build joins a git contributor to an author on an EXACT name match. That misses a
person whenever the two sides spell the name differently -- Semantic Scholar initializes
first names, and git carries nicknames, accents and hyphens. The alias file supplies the
reviewed merges; this script checks it still describes the data before anything applies it.

Checks, and each one is a way the file can rot:
  - every author id it names still exists in the index
  - every git identity it names still appears in the commit log (pass --ids)
  - no id is claimed by two entries, which would chain unrelated people together
  - reports how many people the merge removes and which pairs become one node

Wiring the aliases into build_site.py belongs to the site lane; this script only
validates and reports.

    python3 curate/person_aliases.py --index data/site/halide-index.json
    python3 curate/person_aliases.py --index ... --ids ids.txt   # also check the git side
"""
import argparse
import json
import sys


def load_index(path):
    with open(path) as f:
        data = json.load(f)
    people = {}
    for e in data.get("entries", []):
        if e.get("kind") == "person":
            people[e["id"]] = e
    return people


def git_name(entry):
    """'Name <addr>' -> 'Name'. The commit log is the source of both halves."""
    return entry.split("<")[0].strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--aliases", default="data/pools/person_aliases.json")
    ap.add_argument("--index", default="data/site/halide-index.json")
    ap.add_argument("--ids", help="optional: 'count|Name|email' lines from the commit log")
    args = ap.parse_args()

    with open(args.aliases) as f:
        al = json.load(f)
    people = load_index(args.index)

    known_git = None
    if args.ids:
        known_git = set()
        with open(args.ids) as f:
            for line in f:
                line = line.strip()
                if "|" in line:
                    known_git.add(line.split("|")[0].split(None, 1)[-1].strip())

    errors, warnings, claimed = [], [], {}

    for m in al.get("author_merges", []):
        for pid in [m["keep"]] + m["merge"]:
            if pid not in people:
                errors.append(f"author_merges {m['name']}: id {pid} not in the index")
            if pid in claimed:
                errors.append(f"id {pid} claimed twice: {claimed[pid]} and {m['name']}")
            claimed[pid] = m["name"]

    merged_away = 0
    for a in al.get("contributor_aliases", []):
        aid = a["author"]
        if aid not in people:
            errors.append(f"alias {a['git'][0]}: author id {aid} not in the index")
        for g in a["git"]:
            n = git_name(g)
            if known_git is not None and n not in known_git:
                warnings.append(f"git identity no longer in the commit log: {g}")
            # each git identity that is not already the author's own name is one node removed
            if people.get(aid, {}).get("name") != n:
                merged_away += 1

    if errors:
        print("ERRORS")
        for e in errors:
            print("  -", e)
    if warnings:
        print("WARNINGS")
        for w in warnings:
            print("  -", w)

    print(f"\nauthor-side merges: {len(al.get('author_merges', []))}")
    print(f"contributor aliases: {len(al.get('contributor_aliases', []))}"
          f"  ({sum(a['commits'] for a in al.get('contributor_aliases', []))} commits)")
    print(f"person nodes removed by the merge: ~{merged_away}")
    print(f"left unresolved on purpose: {len(al.get('unresolved', []))}"
          f"  (largest: {max((u['commits'] for u in al.get('unresolved', [])), default=0)} commits)")
    print(f"pairs rejected, and recorded so they are not proposed again: {len(al.get('rejected', []))}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
