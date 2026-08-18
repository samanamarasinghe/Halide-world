#!/usr/bin/env python3
"""Person layer: enriched DOI papers, contributor share, contributor facet, commits sort.

Four files change. Every replacement asserts it matched exactly once, so a file that is not
the expected version fails loudly instead of being half-patched.

    python3 patch_person_layer.py            # report what would change
    python3 patch_person_layer.py --apply
"""
import sys

EDITS = [
    ('build_site.py', [
        ('''def build_doi_only(oc, dup):
    """The 221 works Semantic Scholar's 1,000-result cap hid. DOI and nothing else."""
    retired = duplicate_map(dup)
    out = []
    for doi in (oc or {}).get('dois') or []:
        key = 'oc:' + doi
        entry = {
            'kind': 'paper',
            'tier': 'doi_only',
            'id': key,
            'title': doi,
            'url': 'https://doi.org/' + doi,
            'anchors': [],
            'authors': [],
        }
        if key in retired:
            continue
        out.append(entry)
    return out
''',
         '''def build_doi_only(oc, dup, enriched):
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
'''),

        ('''    for rec in (contributors or {}).get('people', []) if isinstance(contributors, dict) else (contributors or []):
        person = by_name.get(rec.get('name')) or people.get(rec.get('id') or '')
        if not person:
            continue
        person.setdefault('contributions', [])
        person['contributions'].extend(rec.get('repos') or [])

''',
         '''
    # Repo contributors. contributors.py resolves halide/Halide's 359 raw git identities
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

'''),

        ('''    curatable = load('data/pools/lane_b_curatable.json')
    authorship = load('data/pools/authorship.json')
    contributors = load('data/pools/contributors.json')''',
         '''    curatable = load('data/pools/lane_b_curatable.json')
    enriched = load('data/pools/doi_enriched_state.json')
    contributors = load('data/people/halide_contributors.json')
    authorship = load('data/pools/authorship.json')'''),

        ('''    doi_only = build_doi_only(oc, dup)''',
         '''    doi_only = build_doi_only(oc, dup, enriched)'''),

        ('''    people = build_people(papers + [], anchors, authorship, contributors)''',
         '''    people = build_people(papers + doi_only, anchors, authorship, contributors)'''),

        ('''        'people_with_contributions': sum(1 for p in people if p.get('contributions')),''',
         '''        'people_with_contributions': sum(1 for p in people if p.get('contributions')),
        'doi_only_enriched': sum(1 for p in doi_only if p.get('year')),'''),

        ('''        print('NOTE  data/pools/contributors.json absent — no per-repo contribution share')''',
         '''        print('NOTE  data/people/halide_contributors.json absent — no contribution share')
    if not enriched:
        print('NOTE  data/pools/doi_enriched_state.json absent — DOI-only papers stay bare')'''),

    ]),
    ('assets/js/halide-index.js', [
        ("""  var PAPERS_LABELS = { yes: 'Is a paper artifact', no: 'No paper attached' };""",
         """  var PAPERS_LABELS = { yes: 'Is a paper artifact', no: 'No paper attached' };
  var CONTRIB_LABELS = { yes: 'Committed to halide/Halide' };"""),
        ("""    if (facet === 'has_paper') return PAPERS_LABELS[v] || prettify(v);""",
         """    if (facet === 'has_paper') return PAPERS_LABELS[v] || prettify(v);
    if (facet === 'contributor') return CONTRIB_LABELS[v] || prettify(v);"""),
        ("""      case 'anchor_author':
        return rec.anchor_papers || [];""",
         """      case 'anchor_author':
        return rec.anchor_papers || [];
      case 'contributor':
        return rec.contributions && rec.contributions.length ? ['yes'] : [];"""),
        ("""        { key: 'papers_n', label: 'Papers in the index', title: 'How many indexed works the person authored' },""",
         """        { key: 'papers_n', label: 'Papers in the index', title: 'How many indexed works the person authored' },
        { key: 'commits', label: 'Commits to Halide', title: 'Commits to halide/Halide, with the git identities merged. People who never committed sort last' },"""),
        ("""      facets: [
        { facet: 'anchor_author', label: 'Anchor author',""",
         """      facets: [
        { facet: 'contributor', label: 'Halide contributor', optional: true, hint: 'Whether the person has commits in halide/Halide. The commit log is resolved from 359 raw name-and-email identities into people first, so a share is a fraction of the whole tree rather than of one identity. A contributor is joined to an author only on an exact name match; anyone unmatched appears as their own entry.' },
        { facet: 'anchor_author', label: 'Anchor author',"""),
        ("""      papers_n: function (a, b) { return (b.n_papers || 0) - (a.n_papers || 0); },""",
         """      papers_n: function (a, b) { return (b.n_papers || 0) - (a.n_papers || 0); },
      commits: function (a, b) { return (b.contrib_commits || 0) - (a.contrib_commits || 0); },"""),
        ("""    if (rec.kind === 'person') {
      bits.push(rec.n_papers + (rec.n_papers === 1 ? ' paper' : ' papers'));""",
         """    if (rec.kind === 'person') {
      bits.push(rec.n_papers + (rec.n_papers === 1 ? ' paper' : ' papers'));
      (rec.contributions || []).forEach(function (c) {
        bits.push(c.commits + ' commits to ' + c.repo +
          (c.share != null ? ' (' + c.share + '%)' : ''));
      });"""),
        ("""      (rec.contributions || []).forEach(function (c) {
        var row = el('div', 'edge-group');
        row.appendChild(el('span', 'edge-label', 'Contributed'));
        row.appendChild(el('span', 'edge-more',
          (c.share != null ? c.share + '% of ' : '') + (c.repo || '')));
        edges.appendChild(row);
      });""",
         """      (rec.contributions || []).forEach(function (c) {
        var row = el('div', 'edge-group');
        row.appendChild(el('span', 'edge-label', 'Contributed'));
        edgeLink(row, c.repo, c.repo, githubUrl(c.repo));
        row.appendChild(el('span', 'edge-more',
          c.commits + ' commits, ' + c.share + '% of the tree' +
          (c.first ? ', ' + String(c.first).slice(0, 10) + ' to ' + String(c.last).slice(0, 10) : '')));
        edges.appendChild(row);
      });"""),
    ]),
    ('tests/site_smoke.js', [
        ("""  console.log('retired duplicates are gone, not gated');""",
         """  console.log('person layer');
  $('btn-clear').click();
  await settle();
  [...q('.view-btn')].find((b) => b.textContent.startsWith('People')).click();
  await settle();
  const psorts = [...$('sort-within').options].map((o) => o.value);
  check('people offer a commits sort', psorts.indexOf('commits') >= 0);
  $('sort-within').value = 'commits'; $('sort-within').onchange.call($('sort-within'));
  await settle();
  const top = q('.pub-item')[0].querySelector('.pub-dim').textContent;
  // Contribution data only exists once halide_contributors.json is on disk, so the share
  // is asserted when there is one and reported as absent when there is not.
  if (INFO.people_with_contributions) {
    check('top person shows a contribution share', /commits to .+\\(\\d/.test(top), top.trim());
  } else {
    console.log('  --   no contributor data in this payload; share not asserted');
  }

  console.log('retired duplicates are gone, not gated');"""),
    ]),
    ('docs/site.md', [
        ("""| People | authors of indexed papers | anchor author, papers in the index, cites anchor, affiliation\\* |""",
         """| People | authors of indexed papers and halide/Halide committers | Halide contributor\\*, anchor author, papers in the index, cites anchor, affiliation\\* |"""),
        ("""- person → the papers they wrote, and any anchor work they authored""",
         """- person → the papers they wrote, any anchor work they authored, and the repositories they
  committed to with their commit count and share of the tree"""),
        ("""`affiliation` arrives with `data/pools/authorship.json`;""",
         """`affiliation` arrives with `data/pools/authorship.json`; the contributor facet and the
commits sort arrive with `data/people/halide_contributors.json`;"""),
        ("""- **DOI-only records**, the 161 works Semantic Scholar's 1,000-result cap hid. Shown by
  default, since the citation is real and only the metadata is missing.""",
         """- **DOI-only records**, the 161 works Semantic Scholar's 1,000-result cap hid. Shown by
  default, since the citation is real. Where `data/pools/doi_enriched_state.json` has a
  record they carry a real title, venue, year, authors and citation count and keep the tier
  only as provenance; without it they render as bare identifiers."""),
    ]),
]


def main():
    apply = '--apply' in sys.argv
    problems = []
    for path, edits in EDITS:
        try:
            text = open(path).read()
        except OSError as exc:
            problems.append('%s: %s' % (path, exc))
            continue
        done = 0
        for old, new in edits:
            n = text.count(old)
            if n == 1:
                text = text.replace(old, new)
                done += 1
            elif n == 0 and (not new or text.count(new) >= 1):
                done += 1          # already patched, nothing to do
            else:
                problems.append('%s: expected one match, found %d for: %.60s' % (path, n, old.strip()))
        if apply and not problems:
            open(path, 'w').write(text)
        print('%-28s %d/%d edits' % (path, done, len(edits)))
    if problems:
        print('\nNOT PATCHED:')
        for p in problems:
            print('  ' + p)
        sys.exit(1)
    print('\napplied' if apply else '\ndry run — rerun with --apply')


if __name__ == '__main__':
    main()
