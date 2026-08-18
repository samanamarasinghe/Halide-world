#!/usr/bin/env python3
"""Keep the total-contributions figure internal: it orders the list, it does not print.

The number is a normalisation artefact, not a fact about a person, so it has no business on
a card. The sort keeps using it.

Every replacement asserts it matched exactly once, so a file that is not the expected
version fails loudly instead of being half-patched.

    python3 patch_score_internal.py            # report what would change
    python3 patch_score_internal.py --apply
"""
import sys

EDITS = [
    ('assets/js/halide-index.js', [
        ("""      if (sortKey() === 'score') bits.push('total contributions ' + personScore(rec).toFixed(2));\n""",
         ""),
    ]),
    ('tests/site_smoke.js', [
        ("""  const scores = [...q('.pub-item')].map((li) => {
    const m = (li.querySelector('.pub-dim').textContent || '').match(/total contributions ([\\d.]+)/);
    return m ? parseFloat(m[1]) : null;
  }).filter((n) => n !== null);
  let sok = scores.length > 10;
  for (let i = 1; i < scores.length; i++) if (scores[i] > scores[i - 1] + 1e-9) sok = false;
  check('score sort is non-increasing', sok, scores.slice(0, 5).join(','));
  // The figure is only meaningful against the largest values in the index, so the top
  // person must not exceed the two-unit ceiling the normalisation implies.
  check('score stays within its scale', !scores.length || scores[0] <= 2.0001, String(scores[0]));""",
         """  // The figure itself is internal, so the ordering is checked against the payload: rebuild
  // the score from the data and require the rendered names to match its ranking.
  const people = JSON.parse(fs.readFileSync(path.join(ROOT, 'data/site/halide-index.json'), 'utf8'))
    .entries.filter((e) => e.kind === 'person');
  const maxC = Math.max(1, ...people.map((p) => p.contrib_commits || 0));
  const maxP = Math.max(1, ...people.map((p) => p.n_papers || 0));
  const ranked = people
    .map((p) => ({ name: p.name, s: (p.contrib_commits || 0) / maxC + (p.n_papers || 0) / maxP }))
    .sort((a, b) => (b.s - a.s) || String(a.name).localeCompare(String(b.name)))
    .slice(0, 5).map((p) => p.name);
  const rendered = [...q('.pub-item')].slice(0, 5)
    .map((li) => li.querySelector('.pub-title').textContent.trim());
  check('score ranking reaches the page', ranked.join('|') === rendered.join('|'),
    rendered.join('|') + ' vs ' + ranked.join('|'));
  check('the figure itself stays off the card',
    ![...q('.pub-dim')].some((d) => /total contributions/.test(d.textContent)));"""),
    ]),
    ('docs/site.md', [
        ("""load rather than fixed, because both move as the index grows. It is a display ordering, not
a judgement of importance — that is what curation will assign.""",
         """load rather than fixed, because both move as the index grows. The figure is internal: it
orders the list and is not printed on the cards. It is a display ordering, not a judgement
of importance — that is what curation will assign."""),
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
