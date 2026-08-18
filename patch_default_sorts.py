#!/usr/bin/env python3
"""Set what each view opens on, and make Clear filters restore it.

Papers open on citation contexts, anchors on citations within the index; repositories and
people already opened on signature matches and total contributions. Clearing now resets the
sort as well as the facets — without that, a sort chosen once sticks to a view for the rest
of the session and the default becomes unreachable.

Every replacement asserts it matched exactly once, so a file that is not the expected
version fails loudly instead of being half-patched.

    python3 patch_default_sorts.py            # report what would change
    python3 patch_default_sorts.py --apply
"""
import sys

EDITS = [
    ('assets/js/halide-index.js', [
        ("""      sorts: [
        { key: 'cited', label: 'Times cited', title: 'Citations the work itself has drawn — nothing to do with how much Halide is in it' },
        { key: 'year', label: 'Year (newest)', title: 'Newest first' },
        { key: 'contexts', label: 'Citation contexts', title: 'How many passages in the work cite an anchor. A rough proxy for engagement until curation rates it' },
        { key: 'title', label: 'Title (A–Z)', title: 'Alphabetical' }
      ],""",
         """      sorts: [
        { key: 'contexts', label: 'Citation contexts', title: 'How many passages in the work cite an anchor. A rough proxy for engagement until curation rates it' },
        { key: 'cited', label: 'Times cited', title: 'Citations the work itself has drawn — nothing to do with how much Halide is in it' },
        { key: 'year', label: 'Year (newest)', title: 'Newest first' },
        { key: 'title', label: 'Title (A–Z)', title: 'Alphabetical' }
      ],"""),

        ("""      sorts: [
        { key: 'year', label: 'Year (newest)', title: 'Newest first' },
        { key: 'cited_by_pool', label: 'Citations in this index', title: 'How many indexed works cite this anchor' },
        { key: 'title', label: 'Title (A–Z)', title: 'Alphabetical' }
      ],""",
         """      sorts: [
        { key: 'cited_by_pool', label: 'Citations in this index', title: 'How many indexed works cite this anchor' },
        { key: 'year', label: 'Year (newest)', title: 'Newest first' },
        { key: 'title', label: 'Title (A–Z)', title: 'Alphabetical' }
      ],"""),

        ("""    state.minImportance = 0;
    applyFacetDefaults();""",
         """    state.minImportance = 0;
    /* Clearing restores the sort too. Otherwise a sort chosen once sticks to a view for the
       rest of the session with no control that puts it back, and the default a view opens
       on becomes unreachable. */
    state.sort = {};
    buildSortOptions();
    applyFacetDefaults();"""),
    ]),
    ('tests/site_smoke.js', [
        ("""  console.log('total contributions');""",
         """  console.log('default sorts');
  for (const [name, want] of [['Papers', 'contexts'], ['Repositories', 'matches'],
                              ['People', 'score'], ['Anchors', 'cited_by_pool']]) {
    $('btn-clear').click();
    await settle();
    [...q('.view-btn')].find((b) => b.textContent.startsWith(name)).click();
    await settle();
    check(name + ': opens on ' + want, $('sort-within').value === want, $('sort-within').value);
  }

  console.log('total contributions');"""),
    ]),
    ('docs/site.md', [
        ("""## Two rules the page keeps""",
         """## What each view opens on

| View | Default sort | Why |
|---|---|---|
| Papers | Citation contexts | How much the citing work engages with an anchor, rather than its standing elsewhere |
| Repositories | Signature matches | Volume of Halide references in the tree — see the caveat below |
| People | Total contributions | Commits and papers on one axis |
| Anchors | Citations in this index | Which anchor the literature actually builds on |

`Clear filters` restores the sort as well as the facets, so a view's default is always
reachable.

**Signature matches is not an impact measure.** For a repository carrying a vendored Halide
tree the count includes Halide's own files, so it says how much Halide-shaped code sits in
the tree and not how much the project does with it. Sorting by stars is the quicker route to
the projects people actually use.

## Two rules the page keeps"""),
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
