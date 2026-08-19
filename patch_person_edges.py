#!/usr/bin/env python3
"""Wire the contributor and affiliation edges into build_site.py.

The page's person layer was built from paper author lists plus
`data/people/halide_contributors.json`, which covers halide/Halide alone. That
showed 222 people with contribution data out of 886 the contributor lane now
resolves, and no edge on the page carried a category, so the 24 people who
EXTENDED Halide outside the anchor were invisible. Affiliations were read from
`data/pools/authorship.json`, a filename that was never produced; the real
output is `data/pools/affiliation_edges.json`, which is why the page has shown
`people_with_affiliation: 0` since it was built.

This patch is written from the DATA lane against the SITE lane's file, on his
explicit instruction 2026-08-19. Recorded in docs/LANES.md.

Every edit asserts its anchor first: a str.replace that matches nothing writes
the file, reports success, and changes nothing.

    python3 patch_person_edges.py
    python3 build_site.py --write
"""
import os
import sys

TARGET = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'build_site.py')

OLD_CONTRIB = """    # Repo contributors. contributors.py resolves halide/Halide's 359 raw git identities
    # into people and counts their commits, so the share is a real fraction of the tree.
    #
    # A contributor is joined to an author node only on an EXACT display-name or alias
    # match. Anything looser would merge two people who share a surname, and a wrong merge
    # in a person index is worse than two rows for one person: it silently reassigns
    # authorship. Unmatched contributors become their own nodes keyed `git:`.
    rows = (contributors or {}).get('people') or []
    total = sum(r.get('commits') or 0 for r in rows if not r.get('is_bot')) or 1
    for rec in rows:
        if rec.get('is_bot'):
            continue
        name = rec.get('name')
        person = by_name.get(name)
        if not person:
            for alias in rec.get('aliases') or []:
                person = by_name.get(alias)
                if person:
                    break
        if not person:
            person = {'kind': 'person', 'id': 'git:' + str(name), 'title': name,
                      'name': name, 'papers': [], 'anchors': [], 'years': []}
            people['git:' + str(name)] = person
            by_name[name] = person
        share = round(100.0 * (rec.get('commits') or 0) / total, 2)
        person.setdefault('contributions', []).append({
            'repo': 'halide/Halide',
            'commits': rec.get('commits'),
            'share': share,
            'first': rec.get('first_commit'),
            'last': rec.get('last_commit'),
        })
        person['contrib_commits'] = max(person.get('contrib_commits') or 0,
                                        rec.get('commits') or 0)
"""

NEW_CONTRIB = """    # Repo contributors, from contributor_edges.py: 886 merged people over 564 repos,
    # every edge stamped core / extends / packaging / uses. This supersedes the
    # anchor-only file the page used to read, which showed contribution for
    # halide/Halide and nothing else.
    #
    # A contributor is joined to an author node on its hand-reviewed `author_id` first,
    # then on an EXACT display-name or alias match. Anything looser would merge two
    # people who share a surname, and a wrong merge in a person index is worse than two
    # rows for one person: it silently reassigns authorship. Unmatched contributors
    # become their own nodes keyed on the contributor lane's person_id.
    #
    # `share` arrives as a fraction of the repo's Halide-touching commits and is shown
    # as a percentage. It is per-repo, so it is NOT comparable across repos: 91% of a
    # four-person fork is not 91% of Halide.
    edge_index = {}
    for rec in (contrib_edges or {}).get('edges', []):
        edge_index.setdefault(rec['person_id'], []).append(rec)

    for rec in (contrib_edges or {}).get('people', []):
        name = rec.get('name')
        placeholder = (name or '').strip().lower() in PLACEHOLDER_NAMES
        person = None
        if rec.get('author_id'):
            person = people.get(str(rec['author_id']))
        if not person and not placeholder:
            person = by_name.get(name)
        if not person and not placeholder:
            for alias in rec.get('aliases') or []:
                if (alias or '').strip().lower() in PLACEHOLDER_NAMES:
                    continue
                person = by_name.get(alias)
                if person:
                    break
        if not person:
            # Keyed on the contributor lane's own person_id, which is unique, rather
            # than on the display name. Keying on the name merged ten unrelated people
            # onto one `git:unknown` node and two onto `git:root` -- the same failure
            # contributors.py denies at the git layer, reappearing one layer up.
            node_id = rec.get('person_id') or ('git:' + str(name))
            person = {'kind': 'person', 'id': node_id, 'title': name,
                      'name': name, 'papers': [], 'anchors': [], 'years': []}
            people[node_id] = person
            if not placeholder:
                by_name.setdefault(name, person)

        cats = []
        for edge in sorted(edge_index.get(rec['person_id'], []),
                           key=lambda e: -(e.get('commits') or 0)):
            person.setdefault('contributions', []).append({
                'repo': edge['repo'],
                'category': edge.get('category'),
                'commits': edge.get('commits'),
                'share': round(100.0 * (edge.get('share') or 0), 2),
                'first': rec.get('first'),
                'last': rec.get('last'),
            })
            if edge.get('category') and edge['category'] not in cats:
                cats.append(edge['category'])
        if cats:
            # Accumulated, not assigned: two contributor records can land on one author
            # node (S2 abbreviates given names, so `Sander Vocke` joins `S. Vocke` through
            # the reviewed author_id while the display names never match). Assigning let
            # the last record overwrite the first and reported one repo for a person
            # carrying nine.
            for cat in cats:
                if cat not in person.setdefault('contrib_categories', []):
                    person['contrib_categories'].append(cat)
        person['contrib_repos'] = len(person.get('contributions') or [])
        person['contrib_commits_total'] = (person.get('contrib_commits_total') or 0) \\
            + (rec.get('commits') or 0)
        # `contrib_commits` stays COMMITS TO halide/Halide, unchanged, because the People
        # score and its sort are calibrated on it. Cross-repo totals arrive beside it as
        # contrib_commits_total rather than silently reordering the People view.
        core = sum(e.get('commits') or 0
                   for e in edge_index.get(rec['person_id'], [])
                   if e.get('category') == 'core')
        if core:
            person['contrib_commits'] = max(person.get('contrib_commits') or 0, core)
"""

OLD_AFF = """    for rec in (authorship or {}).get('edges', []) if isinstance(authorship, dict) else (authorship or []):
        pid = rec.get('author_id') or ('name:' + str(rec.get('name')))
        person = people.get(pid) or by_name.get(rec.get('name'))
        if not person:
            continue
        aff = rec.get('affiliation') or rec.get('raw_affiliation')
        if aff:
            person.setdefault('affiliations', [])
            if aff not in person['affiliations']:
                person['affiliations'].append(aff)
"""

NEW_AFF = """    # affiliation_edges.py answers "where were they when that happened": every edge is one
    # author on one paper with the institution deposited for it, and `timelines` rolls
    # those into first/last year per institution. Person ids there are POST-DEDUPE
    # canonical, so they key straight onto the author nodes here.
    timelines = (affiliations or {}).get('timelines') or {}
    for pid, entry in timelines.items():
        person = people.get(str(pid)) or by_name.get(entry.get('name'))
        if not person:
            continue
        insts = entry.get('institutions') or {}
        person['affiliations'] = sorted(insts)
        person['affiliation_spans'] = [
            {'institution': name, 'first': span.get('first'), 'last': span.get('last'),
             'n_papers': span.get('n_papers')}
            for name, span in sorted(insts.items(),
                                     key=lambda kv: (kv[1].get('first') or 0))]
        # A person at more than one institution over time is the thing he asked the index
        # to show, so it is a field the page can facet on rather than a computed guess.
        person['n_institutions'] = len(insts)
"""

OLD_SIG = "def build_people(papers, anchors, authorship, contributors):"
NEW_SIG = """# Never a join key. Several unrelated people commit under each of these, and merging is
# transitive, so one placeholder chains them all onto one node. curate/contributors.py
# denies the same set at the git layer; this is the site-side half of that guard.
PLACEHOLDER_NAMES = {
    'unknown', 'user', 'root', 'admin', 'none', 'na', 'nobody', 'your name',
    'ubuntu', 'builder', '',
}


def build_people(papers, anchors, affiliations, contrib_edges):"""

OLD_LOAD = """    contributors = load('data/people/halide_contributors.json')
    authorship = load('data/pools/authorship.json')"""
NEW_LOAD = """    contrib_edges = load('data/pools/contributor_edges.json')
    affiliations = load('data/pools/affiliation_edges.json')"""

OLD_CALL = "    people = build_people(papers + doi_only, anchors, authorship, contributors)"
NEW_CALL = "    people = build_people(papers + doi_only, anchors, affiliations, contrib_edges)"

OLD_NOTE = """    if not authorship:
        print('\\nNOTE  data/pools/authorship.json absent \u2014 no affiliation-at-time-of-paper')
    if not contributors:
        print('NOTE  data/people/halide_contributors.json absent \u2014 no contribution share')"""
NEW_NOTE = """    if not affiliations:
        print('\\nNOTE  data/pools/affiliation_edges.json absent \u2014 no affiliation-at-time-of-paper')
    if not contrib_edges:
        print('NOTE  data/pools/contributor_edges.json absent \u2014 no contribution share')"""

OLD_COUNTS = "        'people_with_contributions': sum(1 for p in people if p.get('contributions')),"
NEW_COUNTS = """        'people_with_contributions': sum(1 for p in people if p.get('contributions')),
        'people_who_extend': sum(1 for p in people
                                 if 'extends' in (p.get('contrib_categories') or [])),
        'people_in_many_repos': sum(1 for p in people if (p.get('contrib_repos') or 0) > 1),
        'people_at_many_institutions': sum(1 for p in people
                                           if (p.get('n_institutions') or 0) > 1),"""

EDITS = [
    ('contributor block', OLD_CONTRIB, NEW_CONTRIB),
    ('affiliation block', OLD_AFF, NEW_AFF),
    ('build_people signature', OLD_SIG, NEW_SIG),
    ('pool loaders', OLD_LOAD, NEW_LOAD),
    ('build_people call', OLD_CALL, NEW_CALL),
    ('absent-file notes', OLD_NOTE, NEW_NOTE),
    ('build-info counts', OLD_COUNTS, NEW_COUNTS),
]


def main():
    text = open(TARGET).read()
    if 'contrib_edges' in text:
        print('build_site.py already patched — nothing to do')
        return 0
    for label, old, new in EDITS:
        n = text.count(old)
        if n != 1:
            sys.exit(f'ABORT: {label} matched {n} times, expected 1. '
                     f'build_site.py is not the version this patch was written against; '
                     f'git pull and retry.')
        text = text.replace(old, new)
    open(TARGET, 'w').write(text)
    compile(text, TARGET, 'exec')
    print(f'patched {TARGET} — {len(EDITS)} edits')
    print('now run: python3 build_site.py --write')
    return 0


if __name__ == '__main__':
    sys.exit(main())
