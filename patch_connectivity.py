#!/usr/bin/env python3
"""Rename the edges control to Show connectivity, and the per-card toggle with it.

"Edges" is the word for the data model; "connectivity" is what a reader of the page is
actually asking for. The behaviour is unchanged.

Every replacement asserts it matched exactly once, so a file that is not the expected
version fails loudly instead of being half-patched.

    python3 patch_connectivity.py            # report what would change
    python3 patch_connectivity.py --apply
"""
import sys

EDITS = [
    ('index.html', [
        ("""title="Open the edge list on every card: the artifacts a paper published, the papers a repository belongs to, the papers a person wrote.">Show edges</button>""",
         """title="Open the connectivity list on every card: the artifacts a paper published, the papers a repository belongs to, the papers a person wrote and the repositories they committed to.">Show connectivity</button>"""),
    ]),
    ('assets/js/halide-index.js', [
        ("""      var setArrow = function (open) { toggle.textContent = open ? 'Edges \\u25be' : 'Edges \\u25b8'; };""",
         """      var setArrow = function (open) {
        toggle.textContent = open ? 'Connectivity \\u25be' : 'Connectivity \\u25b8';
      };"""),
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
