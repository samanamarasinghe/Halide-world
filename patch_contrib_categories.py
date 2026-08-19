#!/usr/bin/env python3
"""Split the Contributions facet by contribution category.

The payload now carries 1,553 contribution edges over 564 repos, each stamped
core / extends / packaging / uses, but the facet still collapses all of them
into one value labelled "Committed to halide/Halide". So a person who only ever
committed to a fork or a downstream project reads as a Halide committer, and
there is no way to ask the page for the 24 people who EXTENDED Halide.

The person card was already correct — it lists every repo with its commit count
— so this is the facet, the labels and the wording around them.

Written from the DATA lane against the SITE lane's file, on his instruction
2026-08-19. Recorded in docs/LANES.md.

    python3 patch_contrib_categories.py
"""
import os
import sys

TARGET = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      'assets', 'js', 'halide-index.js')

OLD_LABELS = "  var CONTRIB_LABELS = { commits: 'Committed to halide/Halide' };"
NEW_LABELS = """  var CONTRIB_LABELS = {
    core: 'Committed to halide/Halide',
    extends: 'Extended Halide',
    uses: 'Committed to a project using Halide',
    packaging: 'Packaged Halide for a distribution'
  };"""

OLD_ORDER = "  var CONTRIB_ORDER = ['commits', '10+', '5-9', '2-4', '1'];"
NEW_ORDER = """  var CONTRIB_ORDER = ['core', 'extends', 'uses', 'packaging',
                      '10+', '5-9', '2-4', '1'];"""

OLD_VALUES = """      case 'contributions':
        var out = [];
        if (rec.contributions && rec.contributions.length) out.push('commits');
        var n = rec.n_papers || 0;
        if (n) out.push(n >= 10 ? '10+' : n >= 5 ? '5-9' : n >= 2 ? '2-4' : '1');
        return out;"""
NEW_VALUES = """      case 'contributions':
        var out = (rec.contrib_categories || []).slice();
        /* A payload built before the categories existed carries contributions with no
           category. Fall back to the old single value rather than dropping the person
           out of a facet whose values are all selected by default. */
        if (!out.length && rec.contributions && rec.contributions.length) out.push('core');
        var n = rec.n_papers || 0;
        if (n) out.push(n >= 10 ? '10+' : n >= 5 ? '5-9' : n >= 2 ? '2-4' : '1');
        return out;"""

OLD_HINT = '{ facet: \'contributions\', label: \'Contributions\', defaultAll: true, hint: \'What the person contributed: how many indexed works they authored, and whether they have commits in halide/Halide. Every value starts selected, so unlighting one removes that group — unlighting "1 paper" is the quickest way to the recurring names. The commit log is resolved from 359 raw name-and-email identities into people first, so a share is a fraction of the whole tree rather than of one identity; a contributor is joined to an author only on an exact name match, and anyone unmatched appears as their own entry.\' }'

NEW_HINT = '{ facet: \'contributions\', label: \'Contributions\', defaultAll: true, hint: \'What the person contributed: how many indexed works they authored, and what kind of code they committed. Committed to halide/Halide is the compiler itself; Extended Halide means they modified it in a fork; the other two are downstream projects and distribution packaging. Every value starts selected, so unlighting one removes that group — unlighting \\"1 paper\\" is the quickest way to the recurring names. Git identities are resolved into people before anything is counted, so a share is a fraction of a repository’s Halide-touching commits rather than of one identity; a contributor is joined to an author on a reviewed alias or an exact name match, and anyone unmatched appears as their own entry.\' }'

OLD_NOTE = "      note: 'Everyone who authored an indexed paper, keyed on their Semantic Scholar author id. ' +\n            'Affiliation at the time of the paper and per-repository contribution share need ' +\n            'authorship.json and the contributors output, which are not in the repository yet — ' +\n            'their facets appear as soon as those files are there.',"

NEW_NOTE = "      note: 'Everyone who authored an indexed paper or committed Halide code, keyed on their ' +\n            'Semantic Scholar author id where there is one. Contribution covers 564 repositories, ' +\n            'not just halide/Halide, and each edge records what kind of contribution it was.',"

OLD_SHARE = "          c.commits + ' commits, ' + c.share + '% of the tree' +"

NEW_SHARE = "          c.commits + ' commits, ' + c.share + '% of that repository’s Halide commits' +"

OLD_SORT = "        { key: 'commits', label: 'Commits to Halide', title: 'Commits to halide/Halide, with the git identities merged. People who never committed sort last' },"

NEW_SORT = "        { key: 'commits', label: 'Commits to Halide', title: 'Commits to halide/Halide itself, with the git identities merged. Commits to the other 563 repositories are on the card but do not move this sort. People who never committed sort last' },"

EDITS = [
    ('contribution labels', OLD_LABELS, NEW_LABELS),
    ('facet value order', OLD_ORDER, NEW_ORDER),
    ('facet values', OLD_VALUES, NEW_VALUES),
    ('facet hint', OLD_HINT, NEW_HINT),
    ('people view note', OLD_NOTE, NEW_NOTE),
    ('share wording on the card', OLD_SHARE, NEW_SHARE),
    ('commits sort title', OLD_SORT, NEW_SORT),
]


def main():
    text = open(TARGET).read()
    if 'Extended Halide' in text:
        print('halide-index.js already patched — nothing to do')
        return 0
    for label, old, new in EDITS:
        n = text.count(old)
        if n != 1:
            sys.exit(f'ABORT: {label} matched {n} times, expected 1. '
                     f'halide-index.js is not the version this patch was written '
                     f'against; git pull and retry.')
        text = text.replace(old, new)
    open(TARGET, 'w').write(text)
    print(f'patched {TARGET} — {len(EDITS)} edits')
    print('reload the page; no rebuild needed, the payload already carries the categories')
    return 0


if __name__ == '__main__':
    sys.exit(main())
