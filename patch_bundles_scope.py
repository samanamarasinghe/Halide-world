#!/usr/bin/env python3
"""Show the vendored-bundles gate on the Repositories view only.

The gate reaches repository records and nothing else, but it sat in the global filter row,
so it rendered on Papers, People and Anchors too — where pressing it fetches a 1.3MB file
and changes nothing.

Every replacement asserts it matched exactly once, so a file that is not the expected
version fails loudly instead of being half-patched.

    python3 patch_bundles_scope.py            # report what would change
    python3 patch_bundles_scope.py --apply
"""
import sys

EDITS = [
    ('assets/js/halide-index.js', [
        ("""    els.searchLabel.firstChild.nodeValue = view().searchLabel;""",
         """    els.searchLabel.firstChild.nodeValue = view().searchLabel;
    /* The bundles gate only reaches repository records, so it belongs to that view rather
       than to the page. Left in the global row it invited a press on Papers or People that
       would fetch a 1.3MB file and change nothing. */
    var bundleBtn = $('btn-bundles');
    if (bundleBtn) bundleBtn.className = 'btn' + (state.view === 'repos' ? '' : ' hidden');"""),
    ]),
    ('tests/site_smoke.js', [
        ("""  console.log('dropped repositories are gone, not gated');""",
         """  console.log('bundles gate belongs to the repositories view');
  for (const name of ['Papers', 'People', 'Anchors']) {
    [...q('.view-btn')].find((b) => b.textContent.startsWith(name)).click();
    await settle();
    check(name + ': bundles button hidden', /hidden/.test($('btn-bundles').className),
      $('btn-bundles').className);
  }
  [...q('.view-btn')].find((b) => b.textContent.startsWith('Repositories')).click();
  await settle();
  check('Repositories: bundles button shown', !/hidden/.test($('btn-bundles').className));

  console.log('dropped repositories are gone, not gated');"""),
    ]),
    ('docs/site.md', [
        ("""- **Vendored bundles**, 2,828 repositories whose only Halide arrived inside a third-party
  dependency. Off by default and shipped in `data/site/halide-bundles.json`, fetched only
  when the button is pressed.""",
         """- **Vendored bundles**, 2,828 repositories whose only Halide arrived inside a third-party
  dependency. Off by default and shipped in `data/site/halide-bundles.json`, fetched only
  when the button is pressed. The button shows on the Repositories view alone, since it
  reaches no other kind of record."""),
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
