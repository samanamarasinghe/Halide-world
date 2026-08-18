#!/usr/bin/env python3
"""Total contributions: commits and papers for a person on one axis.

Commits and papers are on wildly different scales, so ranking people who did both needs a
common axis. The figure is commits divided by the largest commit count in the index plus
papers divided by the largest paper count — each term is a fraction of what that kind of
contribution reaches at its maximum, so someone strong on either side scores near 1 and
someone strong on both scores near 2.

Both denominators are MEASURED at load rather than fixed, because both move as the index
grows: today they are 7,466 commits and 42 papers. It becomes the default People sort, and
the figure shows on the card while that sort is active so the ordering can be checked.

Every replacement asserts it matched exactly once, so a file that is not the expected
version fails loudly instead of being half-patched.

    python3 patch_score.py            # report what would change
    python3 patch_score.py --apply
"""
import sys

EDITS = [
    ('assets/js/halide-index.js', [
        ("""  var UNIVERSE = {};     // view key -> facet -> every value, so a facet keeps its rows""",
         """  var UNIVERSE = {};     // view key -> facet -> every value, so a facet keeps its rows
  /* Denominators for total contributions, measured from the data rather than fixed:
     commits and papers are on wildly different scales, and both maxima move as the index
     grows. Dividing each by its own maximum puts them on the same 0-1 axis. */
  var MAX = { commits: 1, papers: 1 };"""),

        ("""      sorts: [
        { key: 'papers_n', label: 'Papers in the index', title: 'How many indexed works the person authored' },""",
         """      sorts: [
        { key: 'score', label: 'Total contributions', title: 'Commits and papers on one axis: commits divided by the largest commit count, plus papers divided by the largest paper count. Someone strong on either side scores near 1, someone strong on both scores near 2' },
        { key: 'papers_n', label: 'Papers in the index', title: 'How many indexed works the person authored' },"""),

        ("""      commits: function (a, b) { return (b.contrib_commits || 0) - (a.contrib_commits || 0); },""",
         """      commits: function (a, b) { return (b.contrib_commits || 0) - (a.contrib_commits || 0); },
      score: function (a, b) { return personScore(b) - personScore(a); },"""),

        ("""  /* ---------- Sorting ---------- */""",
         """  /* ---------- Sorting ---------- */
  /* Commits and papers measure different things and neither subsumes the other, so total
     contributions adds them rather than picking one: each is a fraction of the largest
     value that kind reaches in this index. It is a display ordering, not a judgement of
     importance -- that is what curation will assign. */
  function personScore(rec) {
    return (rec.contrib_commits || 0) / MAX.commits + (rec.n_papers || 0) / MAX.papers;
  }
"""),

        ("""  function computeUniverse() {""",
         """  function computeMaxima() {
    MAX = { commits: 1, papers: 1 };
    activeData().forEach(function (rec) {
      if (rec.kind !== 'person') return;
      if ((rec.contrib_commits || 0) > MAX.commits) MAX.commits = rec.contrib_commits;
      if ((rec.n_papers || 0) > MAX.papers) MAX.papers = rec.n_papers;
    });
  }

  function computeUniverse() {"""),

        ("""        indexNodes(BUNDLES);
        computeUniverse();
        applyFacetDefaults();""",
         """        indexNodes(BUNDLES);
        computeUniverse();
        computeMaxima();
        applyFacetDefaults();"""),

        ("""        indexNodes(DATA);
        computeUniverse();
        applyFacetDefaults();""",
         """        indexNodes(DATA);
        computeUniverse();
        computeMaxima();
        applyFacetDefaults();"""),

        ("""      bits.push(rec.n_papers + (rec.n_papers === 1 ? ' paper' : ' papers'));""",
         """      bits.push(rec.n_papers + (rec.n_papers === 1 ? ' paper' : ' papers'));
      if (sortKey() === 'score') bits.push('total contributions ' + personScore(rec).toFixed(2));"""),
    ]),
    ('tests/site_smoke.js', [
        ("""  console.log('contributions facet');""",
         """  console.log('total contributions');
  [...q('.view-btn')].find((b) => b.textContent.startsWith('People')).click();
  await settle();
  const ssorts = [...$('sort-within').options].map((o) => o.value);
  check('people offer a combined score sort', ssorts.indexOf('score') >= 0);
  $('sort-within').value = 'score'; $('sort-within').onchange.call($('sort-within'));
  await settle();
  const scores = [...q('.pub-item')].map((li) => {
    const m = (li.querySelector('.pub-dim').textContent || '').match(/total contributions ([\\d.]+)/);
    return m ? parseFloat(m[1]) : null;
  }).filter((n) => n !== null);
  let sok = scores.length > 10;
  for (let i = 1; i < scores.length; i++) if (scores[i] > scores[i - 1] + 1e-9) sok = false;
  check('score sort is non-increasing', sok, scores.slice(0, 5).join(','));
  // The figure is only meaningful against the largest values in the index, so the top
  // person must not exceed the two-unit ceiling the normalisation implies.
  check('score stays within its scale', !scores.length || scores[0] <= 2.0001, String(scores[0]));

  console.log('contributions facet');"""),
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
