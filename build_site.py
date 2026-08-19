#!/usr/bin/env python3
"""Merge the Halide-world pools into data/site/halide-index.json for the web page.

The site is a graph browser: paper, repo and person nodes joined by authorship,
contribution and artifact edges. This script flattens that graph into one payload the
page can hold in memory, and is the only place that knows the pool file layout.

Curation has not run. `role` and `importance` are copied through when a record carries
them and omitted otherwise; the page hides the controls that depend on them until they
appear, so this script and the page both work before and after curation.

Nothing here is judgement. The one derived rule is the duplicate survivor: in every
non-garbage group of data/pools/duplicates.json the first id is the survivor and the rest
are retired, which is the convention that file's own note states. Garbage groups are
title-match artefacts over distinct papers and are never merged.

    python3 build_site.py            # report counts, write nothing
    python3 build_site.py --write    # write data/site/halide-index.json and build-info.json
"""
import argparse
import collections
import datetime
import json
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
POOLS = os.path.join(ROOT, 'data', 'pools')
OUT_DIR = os.path.join(ROOT, 'data', 'site')

# Repos whose only Halide is a vendored third-party copy. They are ordinary records
# carrying an ordinary verdict; the page filters them through the Verdict facet like any
# other, which is why they no longer travel in a file of their own.
BUNDLE = 'third_party_bundle'


def load(path, default=None):
    """Pools that have not been pushed yet are absent, not an error."""
    full = path if os.path.isabs(path) else os.path.join(ROOT, path)
    if not os.path.exists(full):
        return default
    with open(full) as fh:
        return json.load(fh)


def carry_curation(src, dst):
    """Copy the curation fields when they exist. They do not exist yet."""
    for field in ('role', 'importance'):
        if src.get(field) not in (None, '', [], {}):
            dst[field] = src[field]


def duplicate_map(dup):
    """s2_id -> {survivor, kind} for every retired record."""
    retired = {}
    for kind, groups in (dup.get('groups') or {}).items():
        if kind == 'garbage':
            continue
        for group in groups:
            for loser in group[1:]:
                retired[loser] = {'survivor': group[0], 'dup_kind': kind}
    return retired


def build_papers(lane_a, anchors_json, dup, artifacts):
    anchor_ids = set(anchors_json.get('anchors_in_pool') or dup.get('anchors_inside_pool') or [])
    retired = duplicate_map(dup)

    n_retired = [0]
    own = {}          # s2_id -> [repo, ...] the paper's own artifact
    mentioned = {}    # s2_id -> [repo, ...] merely named in the text
    for rec in (artifacts or {}).get('papers', []):
        own[rec['s2_id']] = list(rec.get('own_artifacts') or [])
        mentioned[rec['s2_id']] = [
            link['repo'] for link in rec.get('links') or []
            if link.get('verdict') != 'own_artifact'
        ]

    out = []
    # lane_a.json keys works by s2_id; lane_a_compact.json lists them. Accept either.
    works = lane_a.get('works') or []
    works = list(works.values()) if isinstance(works, dict) else works
    for rec in works:
        s2_id = rec.get('s2_id')
        if s2_id in anchor_ids:
            continue                      # anchors are emitted from anchors.json
        entry = {
            'kind': 'paper',
            'id': s2_id,
            'title': rec.get('title') or 'Untitled',
            'year': rec.get('year'),
            'venue': rec.get('venue'),
            'cited': rec.get('num_cited_by'),
            'fields': rec.get('fields') or [],
            'authors': rec.get('authors') or [],
            'author_ids': rec.get('author_s2_ids') or [],
            'anchors': rec.get('cites_anchors') or [],
            'key_on': rec.get('key_on') or [],
            'intents': rec.get('intents') or [],
            'n_contexts': rec.get('n_contexts') or 0,
            'url': 'https://www.semanticscholar.org/paper/' + s2_id,
        }
        if own.get(s2_id):
            entry['artifacts'] = own[s2_id]
        if mentioned.get(s2_id):
            entry['mentions'] = mentioned[s2_id]
        if s2_id in retired:
            # A retired duplicate is not shown at all: its survivor carries the work, and a
            # page that offers both is offering the same paper twice. The count still gets
            # reported, so the arithmetic from duplicates.json stays checkable.
            n_retired[0] += 1
            continue
        carry_curation(rec, entry)
        out.append(entry)
    return out, anchor_ids, n_retired[0]


def build_anchors(anchors_json, papers):
    """The 15 anchor papers and the Halide repo, with how many pool works cite each."""
    cites = collections.Counter()
    for paper in papers:
        for anchor in paper['anchors']:
            cites[anchor] += 1
    out = []
    for rec in anchors_json.get('anchors') or []:
        entry = {
            'kind': 'anchor',
            'id': rec['id'],
            'title': rec.get('title') or rec['id'],
            'year': rec.get('year'),
            'venue': rec.get('venue'),
            'url': rec.get('url'),
            'authors': rec.get('authors') or [],
            'dois': rec.get('dois') or [],
            'doi_notes': rec.get('doi_notes'),
            'cited_by_pool': cites.get(rec['id'], 0),
        }
        carry_curation(rec, entry)
        out.append(entry)
    return out


def build_doi_only(oc, dup, enriched):
    """The works Semantic Scholar's 1,000-result cap hid.

    `opencitations_only.json` carries a bare DOI and nothing else, so these render as
    identifiers until `enrich_papers.py` has run. Where its state file has a record, the
    paper gets its real title, venue, year, authors and citation count and stops being a
    second-class row — only the `doi_only` tier remains, since the provenance is still
    worth knowing.
    """
    retired = duplicate_map(dup)
    out = []
    for doi in (oc or {}).get('dois') or []:
        key = 'oc:' + doi
        if key in retired:
            continue
        entry = {
            'kind': 'paper',
            'tier': 'doi_only',
            'id': key,
            'title': doi,
            'url': 'https://doi.org/' + doi,
            'anchors': [],
            'authors': [],
        }
        rec = (enriched or {}).get(doi) or {}
        if rec.get('title'):
            entry['title'] = rec['title']
        for src, dst in (('venue', 'venue'), ('year', 'year'), ('cited_by_count', 'cited')):
            if rec.get(src) not in (None, '', []):
                entry[dst] = rec[src]
        names = []
        for author in rec.get('authors') or []:
            name = author.get('name') if isinstance(author, dict) else author
            if name:
                names.append(name)
        if names:
            entry['authors'] = names
        if rec.get('concepts'):
            entry['fields'] = rec['concepts'][:4]
        if rec.get('pdf_url'):
            entry['pdf_url'] = rec['pdf_url']
        carry_curation(rec, entry)
        out.append(entry)
    return out


def build_repos(lane_b, artifacts, curatable, artifact_repos=None):
    """Repo nodes, plus the reverse artifact edge back to the papers that published them.

    `lane_b_classified.json` is the base because it is the only file covering every repo,
    bundles and prose-only included. `lane_b_curatable.json` covers the three source-bearing
    verdicts and carries the cleanup pass's status and the ecosyste.ms metadata, so it is
    merged on top where it has an opinion. Absent, the site is exactly what it was before.

    `artifact_repos.json` is appended after it. Those repos were never found by code search
    -- they are reachable only because a paper named its own artifact -- so they carry NO
    signatures, paths or n_matches. Every one is stamped `discovered_via: artifact_edge`;
    anything reading signature counts must branch on it or it will read zero and conclude
    "no Halide evidence", dropping exactly the repos this lane exists to surface.
    """
    n_dropped = [0]
    extra = {}
    for rec in (curatable or {}).get('repos', []):
        extra[rec['repo']] = rec

    # Edges carry ids only. The page holds every node in memory, so a title stored on the
    # far end of an edge is a second copy of a string it already has -- 5MB of payload
    # became 2MB by dropping them.
    from_paper = collections.defaultdict(list)
    for rec in (artifacts or {}).get('papers', []):
        for repo in rec.get('own_artifacts') or []:
            from_paper[repo].append(rec['s2_id'])

    out = []
    for rec in (lane_b or {}).get('repos', []):
        name = rec['repo']
        entry = {
            'kind': 'repo',
            'id': name,
            'title': name,
            'url': 'https://github.com/' + name,
            'verdict': rec.get('verdict'),
            'evidence': rec.get('evidence'),
            'n_matches': rec.get('n_matches') or 0,
            'signatures': sorted((rec.get('signatures') or {}).keys()),
            'path_kinds': sorted((rec.get('path_kinds') or {}).keys()),
            'paths': (rec.get('paths') or [])[:6],
        }
        clean = extra.get(name) or {}
        meta = clean.get('meta') or {}
        if meta.get('stargazers_count') is not None:
            entry['stars'] = meta['stargazers_count']
        for src, dst in (('description', 'description'), ('language', 'language'),
                         ('pushed_at', 'pushed_at')):
            if meta.get(src):
                entry[dst] = meta[src]
        if clean.get('status'):
            entry['status'] = clean['status']
        if clean.get('flags'):
            entry['flags'] = clean['flags']
        if clean.get('reason'):
            entry['reason'] = clean['reason']
        # A dropped repo carries someone else's Halide-touching source and no relationship
        # of its own, so it does not belong in a browsable index at all. The record still
        # exists in lane_b_curatable.json with its reason, which is where a wrong drop is
        # audited; the page just does not carry it.
        if clean.get('status') == 'drop':
            n_dropped[0] += 1
            continue
        if from_paper.get(name):
            entry['papers'] = from_paper[name]
        carry_curation(rec, entry)
        out.append(entry)

    seen = {e['id'] for e in out}
    for rec in (artifact_repos or {}).get('repos', []):
        name = rec['repo']
        # Hand review rejected these against their own paper: a workload, a substrate or a
        # monorepo the cue happened to sit next to. The reason stays in the pool file so the
        # judgement is auditable; the page just does not carry them.
        if rec.get('head_review') == 'reject' or name in seen:
            continue
        entry = {
            'kind': 'repo',
            'id': name,
            'title': name,
            'url': 'https://github.com/' + name,
            'discovered_via': 'artifact_edge',
            'papers': [p['s2_id'] for p in rec.get('papers') or []],
        }
        for src, dst in (('stars', 'stars'), ('description', 'description'),
                         ('language', 'language')):
            if rec.get(src) is not None:
                entry[dst] = rec[src]
        for flag in ('unverified_name', 'truncated_source_link'):
            if rec.get(flag):
                entry[flag] = True
        carry_curation(rec, entry)
        out.append(entry)
    return out, n_dropped[0]


# Never a join key. Several unrelated people commit under each of these, and merging is
# transitive, so one placeholder chains them all onto one node. curate/contributors.py
# denies the same set at the git layer; this is the site-side half of that guard.
PLACEHOLDER_NAMES = {
    'unknown', 'user', 'root', 'admin', 'none', 'na', 'nobody', 'your name',
    'ubuntu', 'builder', '',
}


def build_people(papers, anchors, affiliations, contrib_edges):
    """Person nodes keyed on the Semantic Scholar author id.

    Built from the paper author lists, which is everything the pushed pools carry. When
    authorship.json and the contributors output arrive they fill affiliation-at-time-of-
    paper and per-repo contribution share, which cannot be derived from the pools here.
    """
    people = {}
    for paper in papers:
        ids = paper.get('author_ids') or []
        names = paper.get('authors') or []
        for i, name in enumerate(names):
            pid = ids[i] if i < len(ids) and ids[i] else 'name:' + name
            person = people.setdefault(pid, {
                'kind': 'person', 'id': pid, 'title': name, 'name': name,
                'papers': [], 'anchors': [], 'years': [],
            })
            person['papers'].append(paper['id'])
            if paper.get('year'):
                person['years'].append(paper['year'])
            for anchor in paper.get('anchors') or []:
                if anchor not in person['anchors']:
                    person['anchors'].append(anchor)

    # Anchor authorship is the one edge that identifies the people who built Halide, and
    # anchors carry names only, so those match on name rather than on an id.
    by_name = {}
    for person in people.values():
        by_name.setdefault(person['name'], person)
    for anchor in anchors:
        for name in anchor.get('authors') or []:
            person = by_name.get(name)
            if not person:
                person = people.setdefault('name:' + name, {
                    'kind': 'person', 'id': 'name:' + name, 'title': name, 'name': name,
                    'papers': [], 'anchors': [], 'years': [],
                })
                by_name[name] = person
            person.setdefault('anchor_papers', [])
            if anchor['id'] not in person['anchor_papers']:
                person['anchor_papers'].append(anchor['id'])

    # Optional enrichment. Absent files leave the fields off the record entirely, and the
    # page hides the facets that depend on them rather than showing an empty list.
    # affiliation_edges.py answers "where were they when that happened": every edge is one
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

    # Repo contributors, from contributor_edges.py: 886 merged people over 564 repos,
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
        person['contrib_commits_total'] = (person.get('contrib_commits_total') or 0) \
            + (rec.get('commits') or 0)
        # `contrib_commits` stays COMMITS TO halide/Halide, unchanged, because the People
        # score and its sort are calibrated on it. Cross-repo totals arrive beside it as
        # contrib_commits_total rather than silently reordering the People view.
        core = sum(e.get('commits') or 0
                   for e in edge_index.get(rec['person_id'], [])
                   if e.get('category') == 'core')
        if core:
            person['contrib_commits'] = max(person.get('contrib_commits') or 0, core)

    out = []
    for person in people.values():
        years = person.pop('years')
        # Anchor works count as papers in the index, because they are: without this an
        # author whose only indexed work is an anchor lands in no band at all and drops out
        # of a facet whose values are all selected.
        person['n_papers'] = len(person['papers']) + len(person.get('anchor_papers') or [])
        if years:
            person['first_year'], person['last_year'] = min(years), max(years)
        out.append(person)
    out.sort(key=lambda p: (-p['n_papers'], p['name']))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--write', action='store_true', help='write the payload')
    args = ap.parse_args()

    lane_a = load('data/pools/lane_a_compact.json') or {}
    lane_b = load('data/pools/lane_b_classified.json') or {}
    dup = load('data/pools/duplicates.json') or {}
    anchors_json = load('data/anchors.json') or {}
    artifacts = load('data/pools/artifacts_attributed.json') or {}
    oc = load('data/pools/opencitations_only.json') or {}
    curatable = load('data/pools/lane_b_curatable.json')
    artifact_repos = load('data/pools/artifact_repos.json')
    enriched = load('data/pools/doi_enriched_state.json')
    contrib_edges = load('data/pools/contributor_edges.json')
    affiliations = load('data/pools/affiliation_edges.json')

    papers, anchor_ids, n_retired = build_papers(lane_a, anchors_json, dup, artifacts)
    anchors = build_anchors(anchors_json, papers)
    doi_only = build_doi_only(oc, dup, enriched)
    repos, n_dropped = build_repos(lane_b, artifacts, curatable, artifact_repos)
    people = build_people(papers + doi_only, anchors, affiliations, contrib_edges)

    entries = anchors + papers + doi_only + repos + people
    curated = sum(1 for e in entries if 'role' in e or 'importance' in e)

    counts = {
        'anchors': len(anchors),
        'papers': len(papers),
        'papers_retired': n_retired,
        'doi_only': len(doi_only),
        'repos': sum(1 for r in repos if r.get('verdict') != BUNDLE),
        'repos_dropped': n_dropped,
        'repos_with_stars': sum(1 for r in repos if r.get('stars') is not None),
        'repos_from_artifact_edges': sum(
            1 for r in repos if r.get('discovered_via') == 'artifact_edge'),
        'bundles': sum(1 for r in repos if r.get('verdict') == BUNDLE),
        'people': len(people),
        'people_with_affiliation': sum(1 for p in people if p.get('affiliations')),
        'people_with_contributions': sum(1 for p in people if p.get('contributions')),
        'people_who_extend': sum(1 for p in people
                                 if 'extends' in (p.get('contrib_categories') or [])),
        'people_in_many_repos': sum(1 for p in people if (p.get('contrib_repos') or 0) > 1),
        'people_at_many_institutions': sum(1 for p in people
                                           if (p.get('n_institutions') or 0) > 1),
        'doi_only_enriched': sum(1 for p in doi_only if p.get('year')),
        'curated': curated,
    }
    for key, value in counts.items():
        print('%-26s %d' % (key, value))
    if not affiliations:
        print('\nNOTE  data/pools/affiliation_edges.json absent — no affiliation-at-time-of-paper')
    if not contrib_edges:
        print('NOTE  data/pools/contributor_edges.json absent — no contribution share')
    if not enriched:
        print('NOTE  data/pools/doi_enriched_state.json absent — DOI-only papers stay bare')
    if not curatable:
        print('NOTE  data/pools/lane_b_curatable.json absent — no stars, no cleanup status')
    if not curated:
        print('NOTE  no record carries role or importance — curation has not run')

    if not args.write:
        return
    os.makedirs(OUT_DIR, exist_ok=True)
    payload = {'schema_version': 1, 'counts': counts, 'entries': entries}
    with open(os.path.join(OUT_DIR, 'halide-index.json'), 'w') as fh:
        json.dump(payload, fh, separators=(',', ':'))
    stale = os.path.join(OUT_DIR, 'halide-bundles.json')
    if os.path.exists(stale):
        os.remove(stale)        # bundles now travel in the main payload
    version = '0.1'
    version_file = os.path.join(ROOT, 'VERSION')
    if os.path.exists(version_file):
        version = open(version_file).read().strip()
    with open(os.path.join(OUT_DIR, 'build-info.json'), 'w') as fh:
        json.dump({
            'version': version,
            'built': datetime.date.today().isoformat(),
            'counts': counts,
        }, fh, indent=1)
    print('\nwrote data/site/halide-index.json and data/site/build-info.json')


if __name__ == '__main__':
    main()
