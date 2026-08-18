#!/usr/bin/env python3
"""Merge the People facets: one Contributions facet, every value selected by default.

Committing to Halide and authoring papers are both contributions, so they belong in one
facet rather than two. All values start lit, which filters nothing but makes removing a
group one click instead of four. Anchor works now count towards a person's paper band, so
an author whose only indexed work is an anchor still lands in a band.

Every replacement asserts it matched exactly once, so a file that is not the expected
version fails loudly instead of being half-patched.

    python3 patch_contributions.py            # report what would change
    python3 patch_contributions.py --apply
"""
import sys

EDITS = [
    ('build_site.py', [
        ("""        person['n_papers'] = len(person['papers'])""",
         """        # Anchor works count as papers in the index, because they are: without this an
        # author whose only indexed work is an anchor lands in no band at all and drops out
        # of a facet whose values are all selected.
        person['n_papers'] = len(person['papers']) + len(person.get('anchor_papers') or [])"""),
    ]),
    ('assets/js/halide-index.js', [
        ("""  var CONTRIB_LABELS = { yes: 'Committed to halide/Halide' };""",
         """  var CONTRIB_LABELS = { commits: 'Committed to halide/Halide' };"""),

        ("""  var BAND_LABELS = { '1': '1 paper', '2-4': '2–4 papers', '5-9': '5–9 papers', '10+': '10 or more' };""",
         """  var BAND_LABELS = { '1': '1 paper', '2-4': '2–4 papers', '5-9': '5–9 papers', '10+': '10 or more' };
  /* Committing sorts above the paper bands however few people did it: it is a different
     kind of contribution, not the smallest one. */
  var CONTRIB_ORDER = ['commits', '10+', '5-9', '2-4', '1'];"""),

        ("""    if (facet === 'contributor') return CONTRIB_LABELS[v] || prettify(v);
    if (facet === 'papers_band') return BAND_LABELS[v] || v;""",
         """    if (facet === 'contributions') return CONTRIB_LABELS[v] || BAND_LABELS[v] || v;"""),

        ("""      case 'papers_band':
        var n = rec.n_papers || 0;
        return [n >= 10 ? '10+' : n >= 5 ? '5-9' : n >= 2 ? '2-4' : '1'];""",
         """      /* Both halves of what a person contributed. Someone can carry a paper band and a
         commit record, and a contributor with no indexed paper carries only the latter --
         which is why zero papers yields no band rather than falling into "1 paper". */
      case 'contributions':
        var out = [];
        if (rec.contributions && rec.contributions.length) out.push('commits');
        var n = rec.n_papers || 0;
        if (n) out.push(n >= 10 ? '10+' : n >= 5 ? '5-9' : n >= 2 ? '2-4' : '1');
        return out;"""),

        ("""      case 'contributor':
        return rec.contributions && rec.contributions.length ? ['yes'] : [];
""", ""),

        ("""        { facet: 'contributor', label: 'Halide contributor', optional: true, hint: 'Whether the person has commits in halide/Halide. The commit log is resolved from 359 raw name-and-email identities into people first, so a share is a fraction of the whole tree rather than of one identity. A contributor is joined to an author only on an exact name match; anyone unmatched appears as their own entry.' },
        { facet: 'anchor_author', label: 'Anchor author', hint: 'People who wrote one of the anchor works themselves: the authors of the Halide papers, matched on name because the anchor records carry names rather than author ids.' },
        { facet: 'papers_band', label: 'Papers in the index', hint: 'How many indexed works the person authored. Most people appear exactly once, so this is the quickest way to the recurring names.' },""",
         """        { facet: 'contributions', label: 'Contributions', defaultAll: true, hint: 'What the person contributed: how many indexed works they authored, and whether they have commits in halide/Halide. Every value starts selected, so unlighting one removes that group — unlighting "1 paper" is the quickest way to the recurring names. The commit log is resolved from 359 raw name-and-email identities into people first, so a share is a fraction of the whole tree rather than of one identity; a contributor is joined to an author only on an exact name match, and anyone unmatched appears as their own entry.' },
        { facet: 'anchor_author', label: 'Anchor author', hint: 'People who wrote one of the anchor works themselves: the authors of the Halide papers, matched on name because the anchor records carry names rather than author ids.' },"""),

        ("""    } else {
      values.sort(function (a, b) {
        var d = (counts[b] || 0) - (counts[a] || 0);
        return d !== 0 ? d : labelFor(facet, a).localeCompare(labelFor(facet, b));
      });
    }""",
         """    } else if (facet === 'contributions') {
      values.sort(function (a, b) {
        return CONTRIB_ORDER.indexOf(a) - CONTRIB_ORDER.indexOf(b);
      });
    } else {
      values.sort(function (a, b) {
        var d = (counts[b] || 0) - (counts[a] || 0);
        return d !== 0 ? d : labelFor(facet, a).localeCompare(labelFor(facet, b));
      });
    }"""),

        ("""  function rebuildFacets() {""",
         """  function applyFacetDefaults() {
    VIEWS.forEach(function (v) {
      v.facets.forEach(function (spec) {
        if (!spec.defaultAll) return;
        var values = (UNIVERSE[v.key] || {})[spec.facet] || [];
        state.sel[spec.facet] = {};
        values.forEach(function (val) { state.sel[spec.facet][val] = true; });
      });
    });
  }

  function rebuildFacets() {"""),

        ("""    state.minImportance = 0;
    els.text.value = '';""",
         """    state.minImportance = 0;
    applyFacetDefaults();
    els.text.value = '';"""),

        ("""        indexNodes(DATA);
        computeUniverse();""",
         """        indexNodes(DATA);
        computeUniverse();
        applyFacetDefaults();"""),

        ("""        BUNDLES = (raw && raw.entries) || [];
        indexNodes(BUNDLES);
        computeUniverse();""",
         """        BUNDLES = (raw && raw.entries) || [];
        indexNodes(BUNDLES);
        computeUniverse();
        applyFacetDefaults();"""),
    ]),
    ('tests/site_smoke.js', [
        ("""  console.log('retired duplicates are gone, not gated');""",
         """  console.log('contributions facet');
  $('btn-clear').click();
  await settle();
  [...q('.view-btn')].find((b) => b.textContent.startsWith('People')).click();
  await settle();
  const cblock = [...q('#filter-grid .filter-block')]
    .find((b) => /Contributions/.test(b.querySelector('.filter-label').textContent));
  check('one merged contributions facet', !!cblock);
  check('no separate contributor facet',
    ![...q('#filter-grid .filter-label')].some((l) => /Halide contributor/.test(l.textContent)));
  if (cblock) {
    const boxes = [...cblock.querySelectorAll('.facet-item input')];
    check('every value starts selected', boxes.length > 0 && boxes.every((b) => b.checked),
      boxes.filter((b) => !b.checked).length + ' unselected');
    // All values lit must filter nothing: everyone carries at least one, including an
    // author whose only indexed work is an anchor and a committer with no paper.
    check('all lit shows the whole view', /^\\(\\d+\\)$/.test($('pubs-count').textContent),
      $('pubs-count').textContent);
    const one = [...cblock.querySelectorAll('.facet-item')].find((l) => /1 paper/.test(l.textContent));
    if (one) {
      const cb2 = one.querySelector('input');
      cb2.checked = false; cb2.onchange.call(cb2);
      await settle();
      check('unlighting a value narrows', /of/.test($('pubs-count').textContent),
        $('pubs-count').textContent);
      $('btn-clear').click();
      await settle();
      check('clear relights every value',
        [...q('#filter-grid .facet-item input')].filter((b) => !b.checked).length >= 0);
    }
  }

  console.log('retired duplicates are gone, not gated');"""),
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
