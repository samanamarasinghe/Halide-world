#!/usr/bin/env python3
"""Drop the kind badge from person cards.

Every view is single-kind — People shows only people — so a "Person" badge on
every card in the People view labels the one thing the reader already knows.

His call 2026-08-19. Written from the DATA lane against the SITE lane's file;
recorded in docs/LANES.md.

Note the same redundancy exists on Papers, Repositories and Anchors, which are
also single-kind views. Left alone: he asked about People.

    python3 patch_person_badge.py
"""
import os
import sys

TARGET = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      'assets', 'js', 'halide-index.js')

OLD = ("    var meta = el('div', 'pub-meta');\n"
       "    meta.appendChild(el('span', 'badge badge-' + rec.kind, "
       "KIND_LABELS[rec.kind] || rec.kind));")
NEW = ("    var meta = el('div', 'pub-meta');\n"
       "    /* No kind badge on people. Every view is single-kind, so the badge names the\n"
       "       one thing the reader already knows from the view they are in. The other\n"
       "       three views keep theirs for now. */\n"
       "    if (rec.kind !== 'person') {\n"
       "      meta.appendChild(el('span', 'badge badge-' + rec.kind, "
       "KIND_LABELS[rec.kind] || rec.kind));\n"
       "    }")

# The smoke test proved "the author click landed on a person" by asserting a
# .badge-person exists. With the badge gone it must assert the same fact from
# something that survives: the click filters the People view down to that one name.
TEST = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tests', 'site_smoke.js')

OLD_TEST = ("    check('author click lands on the person', "
            "q('.pub-item .badge-person').length === 1);")
NEW_TEST = ("    const landed = q('.pub-item');\n"
            "    const onPeople = /People/.test([...q('.view-btn')]\n"
            "      .find((b) => b.className.indexOf('active') >= 0).textContent);\n"
            "    check('author click lands on the person',\n"
            "      landed.length === 1 && onPeople "
            "&& landed[0].textContent.indexOf(person.textContent) >= 0);")

EDITS = [('kind badge', OLD, NEW)]
TEST_EDITS = [('smoke assertion', OLD_TEST, NEW_TEST)]


def main():
    text = open(TARGET).read()
    if "rec.kind !== 'person') {\n      meta.appendChild" in text:
        print('halide-index.js already patched — nothing to do')
        return 0
    for label, old, new in EDITS:
        n = text.count(old)
        if n != 1:
            sys.exit(f'ABORT: {label} matched {n} times, expected 1. '
                     f'git pull and retry.')
        text = text.replace(old, new)
    open(TARGET, 'w').write(text)

    tests = open(TEST).read()
    for label, old, new in TEST_EDITS:
        n = tests.count(old)
        if n != 1:
            sys.exit(f'ABORT: {label} matched {n} times, expected 1. '
                     f'git pull and retry.')
        tests = tests.replace(old, new)
    open(TEST, 'w').write(tests)
    print(f'patched {TARGET} and {TEST}')
    print('reload the page; no rebuild needed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
