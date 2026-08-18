#!/usr/bin/env python3
"""Resolve halide/Halide git identities to people, and measure contribution.

`halide/Halide` has no .mailmap, so 23,755 commits arrive under 359 distinct
(name, email) pairs covering 336 emails -- but far fewer actual people. Google
corporate machines mint a fresh address per host, so one contributor appears
under eighteen emails; others commit under a display name and a GitHub handle.
Any contribution share computed before merging these is wrong: Dillon Sharlet is
understated by 11% and Connelly Barnes by 44%.

Identities are merged with a union-find over four keys:

    exact email  |  normalised display name  |  GitHub noreply handle  |
    email local-part

Two rules that matter more than they look:

  * Placeholder names are DENIED from the name key. `unknown` is used as a
    display name by four different people here -- Andrew Adams, Khouri Giordano,
    a TNO contributor and a nightly bot. Because merging is transitive, letting
    `unknown` act as a key chains all four into one person and credits
    Giordano's commits to Adams. Placeholders must never be a merge key.

  * Over-merging is worse than under-merging. Under-merging leaves a person
    split, which is visible and fixable; over-merging silently attributes one
    person's work to another and looks perfectly plausible in a chart. When a
    rule is uncertain, leave the split and record it in MANUAL_ALIASES.

Requires a clone. A blobless one is enough and is 27MB rather than gigabytes:

    git clone --bare --filter=blob:none https://github.com/halide/Halide.git
    python3 curate/contributors.py --repo Halide.git --out data/people/halide_contributors.json
"""

import argparse
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict

NOREPLY = re.compile(r"^(?:\d+\+)?([^@]+)@users\.noreply\.github\.com$", re.I)
BOTS = re.compile(r"nightly|dependabot|\[bot\]|github-actions", re.I)

# Never a merge key: several unrelated people commit under these display names.
PLACEHOLDER_NAMES = {
    "unknown", "user", "root", "admin", "none", "na", "nobody", "your name",
    "ubuntu", "builder", "",
}
# Never a merge key as an email local-part: shared across organisations.
GENERIC_LOCALPARTS = {
    "admin", "root", "user", "me", "info", "dev", "build", "ci", "test", "git",
    "github", "none", "noreply", "mail", "email", "bot",
}

# Splits the automatic rules cannot close, resolved by hand. `dsharlet-intel`
# <dillon.sharlet@intel.com> is Dillon Sharlet after moving from Google to
# Intel: no shared email, no shared name, and the local-parts differ
# (`dsharlet` vs `dillon.sharlet`). Only a human knows. Each entry maps an
# identity to the canonical name it belongs to.
MANUAL_ALIASES = {
    ("dsharlet-intel", "dillon.sharlet@intel.com"): "Dillon Sharlet",
}


def normalize_name(name):
    return re.sub(r"[^a-z ]", "", re.sub(r"\s+", " ", name.strip().lower())).strip()


def read_log(repo):
    output = subprocess.run(
        ["git", "-C", repo, "log", "--format=%aN\t%aE\t%ad", "--date=short"],
        capture_output=True, text=True, check=True,
    ).stdout
    return [tuple(line.split("\t")) for line in output.strip().split("\n")
            if line.count("\t") == 2]


class UnionFind:
    def __init__(self):
        self.parent = {}

    def find(self, item):
        self.parent.setdefault(item, item)
        while self.parent[item] != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return item

    def union(self, a, b):
        root_a, root_b = self.find(a), self.find(b)
        if root_a != root_b:
            self.parent[root_a] = root_b


def merge_identities(commits):
    uf = UnionFind()
    canonical_key = {}
    for name, email, _ in commits:
        address = email.lower().strip()
        identity = ("id", name, address)
        uf.union(identity, ("email", address))

        normalized = normalize_name(name)
        if normalized and normalized not in PLACEHOLDER_NAMES:
            uf.union(identity, ("name", normalized))

        handle = NOREPLY.match(address)
        if handle:
            uf.union(identity, ("gh", handle.group(1).lower()))
        else:
            local = address.split("@")[0]
            if len(local) >= 4 and local not in GENERIC_LOCALPARTS:
                uf.union(identity, ("localpart", local))

        target = MANUAL_ALIASES.get((name, address))
        if target:
            uf.union(identity, ("name", normalize_name(target)))
            canonical_key[identity] = target
    return uf


def aggregate(commits, uf):
    people = defaultdict(lambda: {
        "commits": 0, "names": Counter(), "emails": set(),
        "first_commit": None, "last_commit": None,
    })
    for name, email, date in commits:
        address = email.lower().strip()
        person = people[uf.find(("id", name, address))]
        person["commits"] += 1
        person["names"][name] += 1
        person["emails"].add(address)
        if person["first_commit"] is None or date < person["first_commit"]:
            person["first_commit"] = date
        if person["last_commit"] is None or date > person["last_commit"]:
            person["last_commit"] = date

    rows = []
    for person in people.values():
        display = person["names"].most_common(1)[0][0]
        rows.append({
            "name": display,
            "aliases": sorted(n for n in person["names"] if n != display),
            "emails": sorted(person["emails"]),
            "commits": person["commits"],
            "first_commit": person["first_commit"],
            "last_commit": person["last_commit"],
            "is_bot": bool(BOTS.search(display) or
                           any(BOTS.search(e) for e in person["emails"])),
        })
    return sorted(rows, key=lambda r: -r["commits"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default="Halide.git")
    parser.add_argument("--out", default="data/people/halide_contributors.json")
    args = parser.parse_args()

    commits = read_log(args.repo)
    uf = merge_identities(commits)
    people = aggregate(commits, uf)

    humans = [p for p in people if not p["is_bot"]]
    total = sum(p["commits"] for p in humans)
    identities = len({(n, e) for n, e, _ in commits})
    emails = len({e.lower() for _, e, _ in commits})

    print(f"commits {len(commits)}  raw identities {identities}  emails {emails}")
    print(f"people {len(people)}  ({len(people) - len(humans)} bots excluded)")
    print(f"\n{'person':26s} {'commits':>7s} {'%':>6s} {'names':>5s} {'emails':>6s}  span")
    for person in humans[:20]:
        print(f"{person['name'][:26]:26s} {person['commits']:7d} "
              f"{100 * person['commits'] / total:5.1f}% "
              f"{1 + len(person['aliases']):5d} {len(person['emails']):6d}  "
              f"{person['first_commit']}..{person['last_commit']}")

    for cut in (1, 5, 10, 25, 50, 100):
        share = sum(p["commits"] for p in humans[:cut]) / total
        print(f"  top {cut:3d} = {100 * share:5.1f}% of commits")

    import os
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w") as handle:
        json.dump({"schema_version": 1, "n_people": len(people),
                   "n_commits": len(commits), "people": people}, handle, indent=1)
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
