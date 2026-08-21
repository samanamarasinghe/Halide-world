#!/usr/bin/env python3
"""Apply person_aliases.json author_merges in build_site.py's person layer.

curate/person_aliases.py validates the merges but nothing applied them: build_people
keyed person nodes on the raw per-paper author id, so every merged identity still
rendered as its own card (five Amarasinghe cards after the 2026-08-21 big dedupe).
This patch remaps each author id to its keep id as the nodes are built, names the
node from the alias entry, and registers the absorbed spellings in the by-name join
so anchor authorship still lands on the merged node instead of minting a name: node.

    python3 patch_author_merges.py && python3 build_site.py --write
"""
import sys

PATH = 'build_site.py'
src = open(PATH).read()

OLD_DOC = '''    paper and per-repo contribution share, which cannot be derived from the pools here.
    """
    people = {}'''
NEW_DOC = '''    paper and per-repo contribution share, which cannot be derived from the pools here.

    data/pools/person_aliases.json author_merges collapse ids the dedupe proved are one
    person: every merged id keys onto its keep id here and the node takes the alias
    entry's name, with the absorbed spellings kept in alt_names for the by-name join.
    An absent alias file means no remap, like every other optional pool.
    """
    import json as _json, os as _os
    remap, alias_names = {}, {}
    _ap = _os.path.join('data', 'pools', 'person_aliases.json')
    if _os.path.exists(_ap):
        with open(_ap) as _f:
            for _m in (_json.load(_f).get('author_merges') or []):
                _keep = str(_m.get('keep') or '')
                if not _keep:
                    continue
                if _m.get('name'):
                    alias_names[_keep] = _m['name']
                for _mid in (_m.get('merge') or []):
                    remap[str(_mid)] = _keep
    people = {}'''

OLD_NODE = '''            pid = ids[i] if i < len(ids) and ids[i] else 'name:' + name
            person = people.setdefault(pid, {
                'kind': 'person', 'id': pid, 'title': name, 'name': name,
                'papers': [], 'anchors': [], 'years': [],
            })'''
NEW_NODE = '''            pid = ids[i] if i < len(ids) and ids[i] else 'name:' + name
            pid = remap.get(str(pid), str(pid))
            raw_name = name
            name = alias_names.get(pid, name)
            person = people.setdefault(pid, {
                'kind': 'person', 'id': pid, 'title': name, 'name': name,
                'papers': [], 'anchors': [], 'years': [],
            })
            if raw_name != name and raw_name not in person.setdefault('alt_names', []):
                person['alt_names'].append(raw_name)'''

OLD_BYNAME = '''    by_name = {}
    for person in people.values():
        by_name.setdefault(person['name'], person)'''
NEW_BYNAME = '''    by_name = {}
    for person in people.values():
        by_name.setdefault(person['name'], person)
        for _alt in person.get('alt_names') or []:
            by_name.setdefault(_alt, person)'''

for old, new, tag in ((OLD_DOC, NEW_DOC, 'alias-load'),
                      (OLD_NODE, NEW_NODE, 'id-remap'),
                      (OLD_BYNAME, NEW_BYNAME, 'by-name')):
    n = src.count(old)
    if n != 1:
        sys.exit(f'ABORT: {tag} anchor matched {n} times, expected exactly 1 -- '
                 f'build_site.py has diverged, patch nothing')
    src = src.replace(old, new)

open(PATH, 'w').write(src)
print('patched build_site.py: author_merges now applied in build_people')
