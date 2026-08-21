"""The big name dedupe: collapse Semantic Scholar author ids that are one person.

S2 splits a person across ids by name spelling -- `S. Amarasinghe`, `Saman
Amarasinghe`, `Saman P. Amarasinghe` and a fourth identical-name id are all him,
and the pool holds 1,057 such name-compatible same-surname pairs over 5,688 ids.
The build's exact-name auto-match cannot see these, and the 2026-08-19 ruling
stands: name shape alone is never a merge key. This script generates
`author_merges` entries for data/pools/person_aliases.json from independent
evidence, and everything it cannot prove goes to a review queue, not a merge.

Signals, in order of authority (measured 2026-08-21):
  ORCID match     -> merge; mismatch -> BLOCK, even over coauthor overlap.
                     21 coauth-supported pairs were blocked this way; two
                     different Tianqi Chens share 9 coauthors, so coauthors
                     alone do lie. ORCID itself is imperfect (Alex Aiken holds
                     two ORCID records), so a cluster containing an internal
                     mismatch is never auto-merged -- it is queued whole.
  coauthor overlap >=1 (his ruling) -> merge. Base rate on certain-negatives
                     (same surname, incompatible given names): 1.4%.
  OpenAlex author id match -> merge (rescued the Emer pair, which has no ORCID).

ORCID/OpenAlex-id harvest: DOI per paper from data/pools/s2_doi_map.json
(curate/resolve_dois.py), then one OpenAlex works request per DOI --
single-entity requests with mailto; batch `filter=doi:a|b|...` calls draw an
instant 429 without a key. OpenAlex authorships join to S2 author ids by
surname-within-one-paper, the same rule as the affiliation lane; a surname
appearing twice on one author list is skipped, never guessed. OpenAlex is
consulted for ORCID and its author id only, never affiliations (standing rule).

Run after resolve_dois.py; writes author_merges_generated.json,
data/pools/author_ids_external.json and data/pools/dedupe_review_queue.md.
Measured run 2026-08-21: 3,236/5,688 ids gained an ORCID, 4,373 an OpenAlex
author id; 557 accepted pairs -> 346 clusters, 443 ids retired (5,688 -> 5,245).

    python3 curate/dedupe_authors.py        # from the repo root, after resolve_dois.py
                                            # (edit MAILTO below before running)
"""


# ============ stage: build_profiles ============
import json, unicodedata, re
from collections import defaultdict

d = json.load(open('data/pools/lane_a_compact.json'))
works = d['works'] if isinstance(d, dict) and 'works' in d else d
items = list(works.items()) if isinstance(works, dict) else list(enumerate(works))

def strip_acc(s):
    return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')

PARTICLES = {'van','von','de','der','den','del','della','di','da','dos','la','le','bin','al','ben','mac','mc','st'}

def parse(name):
    n = strip_acc(name).lower().replace('.', ' ').replace('-', ' ')
    n = re.sub(r'[^a-z ]', ' ', n)
    toks = [t for t in n.split() if t]
    if not toks: return None
    # surname: trailing token, absorbing particles
    i = len(toks) - 1
    sur = [toks[i]]
    while i-1 >= 1 and toks[i-1] in PARTICLES:
        i -= 1; sur.insert(0, toks[i])
    surname = ' '.join(sur)
    given = toks[:i]
    return surname, given

prof = defaultdict(lambda: {'names': set(), 'papers': set(), 'years': set(),
                            'venues': set(), 'coauth': set(), 'fields': set(),
                            'same_paper_ids': set()})
for k, w in items:
    names = w.get('authors', []) or []
    ids = w.get('author_s2_ids', []) or []
    sid = str(w.get('s2_id', k))
    row = [(names[i], str(ids[i])) for i in range(min(len(names), len(ids))) if ids[i]]
    allids = {a for _, a in row}
    for nm, aid in row:
        p = prof[aid]
        p['names'].add(nm); p['papers'].add(sid)
        if w.get('year'): p['years'].add(w['year'])
        if w.get('venue'): p['venues'].add(w['venue'])
        p['coauth'] |= (allids - {aid})
        p['same_paper_ids'] |= (allids - {aid})
        for f in (w.get('fields') or []): p['fields'].add(f)

out = {}
for aid, p in prof.items():
    parsed = [parse(n) for n in p['names']]
    parsed = [x for x in parsed if x]
    out[aid] = {'names': sorted(p['names']), 'surnames': sorted({s for s, _ in parsed}),
                'givens': [g for _, g in parsed],
                'n_papers': len(p['papers']), 'papers': sorted(p['papers']),
                'years': sorted(p['years']), 'venues': sorted(p['venues']),
                'coauth': sorted(p['coauth']), 'fields': sorted(p['fields'])}
json.dump(out, open('profiles.json', 'w'))
print('author ids:', len(out))
sur = defaultdict(int)
for a, v in out.items():
    for s in v['surnames']: sur[s] += 1
print('distinct surnames:', len(sur))
print('ids in surname buckets of size>1:', sum(c for c in sur.values() if c > 1))
print('largest buckets:', sorted(sur.items(), key=lambda x: -x[1])[:12])


# ============ stage: candidates ============
import json, itertools
from collections import defaultdict

P = json.load(open('profiles.json'))

def tok_match(a, b):
    if len(a) > 1 and len(b) > 1: return a == b
    return a[0] == b[0]

def seq_compat(g1, g2):
    """g1, g2 given-token lists. True if one aligns into the other in order."""
    if not g1 or not g2: return False
    if not tok_match(g1[0], g2[0]): return False
    short, lng = (g1, g2) if len(g1) <= len(g2) else (g2, g1)
    i = 0
    for t in lng:
        if i < len(short) and tok_match(short[i], t): i += 1
    return i == len(short)

def name_compat(a, b):
    for g1 in P[a]['givens']:
        for g2 in P[b]['givens']:
            if seq_compat(g1, g2): return True
    return False

def relation(a, b):
    na = {n.lower() for n in P[a]['names']}; nb = {n.lower() for n in P[b]['names']}
    if na & nb: return 'identical-name'
    ia = any(len(t) == 1 for g in P[a]['givens'] for t in g)
    ib = any(len(t) == 1 for g in P[b]['givens'] for t in g)
    if ia != ib: return 'initial-expansion'
    la = max((len(g) for g in P[a]['givens']), default=0)
    lb = max((len(g) for g in P[b]['givens']), default=0)
    if la != lb: return 'middle-token-differs'
    return 'other'

buckets = defaultdict(list)
for aid, v in P.items():
    for s in v['surnames']: buckets[s].append(aid)

pairs = []
for s, ids in buckets.items():
    if len(ids) < 2: continue
    for a, b in itertools.combinations(sorted(ids), 2):
        if not name_compat(a, b): continue
        A, B = P[a], P[b]
        co = set(A['coauth']) & set(B['coauth']) - {a, b}
        same_paper = bool(set(A['papers']) & set(B['papers']))
        pairs.append({
            'a': a, 'b': b, 'surname': s,
            'names': [A['names'], B['names']],
            'relation': relation(a, b),
            'coauthors_shared': len(co),
            'shared_coauthor_ids': sorted(co)[:8],
            'same_paper': same_paper,
            'venues_shared': len(set(A['venues']) & set(B['venues'])),
            'fields_shared': len(set(A['fields']) & set(B['fields'])),
            'bucket_size': len(ids),
            'n_papers': [A['n_papers'], B['n_papers']],
        })
json.dump(pairs, open('candidates.json', 'w'))

print('candidate pairs:', len(pairs))
by_rel = defaultdict(int)
for p in pairs: by_rel[p['relation']] += 1
print('by relation:', dict(by_rel))
print('with >=1 shared coauthor:', sum(1 for p in pairs if p['coauthors_shared'] >= 1))
print('with >=2 shared coauthors:', sum(1 for p in pairs if p['coauthors_shared'] >= 2))
print('co-occur on one paper (auto-negative):', sum(1 for p in pairs if p['same_paper']))
print('no signal at all:', sum(1 for p in pairs if not p['same_paper'] and p['coauthors_shared'] == 0))
big = sorted(pairs, key=lambda p: -p['bucket_size'])[:1]
print('pairs in buckets >=50 ids:', sum(1 for p in pairs if p['bucket_size'] >= 50))


# ============ stage: orcid_harvest ============
import json, sys, time, unicodedata, urllib.parse, urllib.request
from collections import defaultdict

MAILTO = 'saman@csail.mit.edu'

def strip_acc(s):
    return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c)!='Mn')
def surname(name):
    toks = [t for t in strip_acc(name).lower().replace('.',' ').replace('-',' ').split() if t]
    return toks[-1] if toks else None

doimap = json.load(open('data/pools/s2_doi_map.json'))
lane = json.load(open('data/pools/lane_a.json'))['works']
doi2sid = {}
for sid, rec in doimap.items():
    d = rec.get('doi')
    if d and sid in lane:
        doi2sid[d.lower().strip()] = sid

limit = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else None
dois = sorted(doi2sid)[:limit] if limit else sorted(doi2sid)
print(f'{len(doi2sid)} DOIs mapped to pool papers; fetching {len(dois)}')

state_path = 'orcid_state.json'
try: state = json.load(open(state_path))
except FileNotFoundError: state = {}
todo = [d for d in dois if d not in state]
done = 0
for d in todo:
    url = f'https://api.openalex.org/works/doi:{urllib.parse.quote(d, safe="")}?mailto={MAILTO}&select=doi,authorships'
    wrk = None
    for attempt in range(6):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                wrk = json.load(r)
            break
        except urllib.error.HTTPError as e:
            if e.code == 404: wrk = {}; break
            time.sleep(8 * (attempt + 1) if e.code == 429 else 4)
        except Exception:
            time.sleep(4)
    if wrk is None:
        state[d] = {'s2_id': doi2sid[d], 'authors': None, 'error': 'retries'}
    elif not wrk:
        state[d] = {'s2_id': doi2sid[d], 'authors': None}
    else:
        auths = []
        for a in wrk.get('authorships', []):
            au = a.get('author') or {}
            auths.append({'name': au.get('display_name'),
                          'orcid': (au.get('orcid') or '').replace('https://orcid.org/','') or None,
                          'oa_id': (au.get('id') or '').replace('https://openalex.org/','') or None})
        state[d] = {'s2_id': doi2sid[d], 'authors': auths}
    done += 1
    if done % 25 == 0:
        json.dump(state, open(state_path, 'w'))
        n_hit = sum(1 for v in state.values() if v.get('authors'))
        print(f'  {done}/{len(todo)}  in OpenAlex {n_hit}', flush=True)
    time.sleep(0.9)
json.dump(state, open(state_path, 'w'))

# join to S2 author ids by surname-within-paper
sid2aid_orcid, sid_skipdup = {}, 0
orcid_of = defaultdict(set); oaid_of = defaultdict(set)
matched = mismatched = 0
for d, rec in state.items():
    if not rec.get('authors'): continue
    sid = rec['s2_id']; w = lane.get(sid)
    if not w: continue
    s2_by_sur = defaultdict(list)
    for a in w['authors']:
        if a.get('s2_author_id'): s2_by_sur[surname(a['name'])].append(str(a['s2_author_id']))
    oa_by_sur = defaultdict(list)
    for a in rec['authors']:
        if a['name']: oa_by_sur[surname(a['name'])].append(a)
    for sur, s2ids in s2_by_sur.items():
        oas = oa_by_sur.get(sur, [])
        if len(s2ids) != 1 or len(oas) != 1:
            if len(s2ids) > 1 or len(oas) > 1: sid_skipdup += 1
            continue
        matched += 1
        if oas[0]['orcid']: orcid_of[s2ids[0]].add(oas[0]['orcid'])
        if oas[0]['oa_id']: oaid_of[s2ids[0]].add(oas[0]['oa_id'])
json.dump({'orcid': {k: sorted(v) for k,v in orcid_of.items()},
           'oa_id': {k: sorted(v) for k,v in oaid_of.items()}},
          open('data/pools/author_ids_external.json','w'), indent=1)
print(f'author-slot matches: {matched}, dup-surname slots skipped: {sid_skipdup}')
print(f'S2 ids with an ORCID: {len(orcid_of)}   with an OpenAlex author id: {len(oaid_of)}')
multi = [k for k,v in orcid_of.items() if len(v)>1]
print(f'S2 ids carrying >1 ORCID (conflict, inspect): {len(multi)}')


# ============ stage: score ============
import json
from collections import defaultdict
P=json.load(open('profiles.json')); C=json.load(open('candidates.json'))
E=json.load(open('data/pools/author_ids_external.json'))
orc={k:set(v) for k,v in E['orcid'].items()}; oa={k:set(v) for k,v in E['oa_id'].items()}
conflicted={k for k,v in orc.items() if len(v)>1}

def verdict(p):
    a,b=p['a'],p['b']
    oa_m = bool(oa.get(a,set()) & oa.get(b,set()))
    if a in orc and b in orc and a not in conflicted and b not in conflicted:
        om = bool(orc[a] & orc[b])
        return ('orcid-match' if om else 'orcid-mismatch'), oa_m
    if orc.get(a,set()) & orc.get(b,set()): return 'orcid-match', oa_m  # conflicted but overlapping
    return 'orcid-absent', oa_m

stats=defaultdict(int); rows=[]
for p in C:
    ov, oam = verdict(p); co = p['coauthors_shared']>=1
    stats[(ov, oam, co)]+=1
    rows.append({**p,'orcid':ov,'oa_id_match':oam})
json.dump(rows, open('scored.json','w'))

def n(f): return sum(v for k,v in stats.items() if f(*k))
print('of 1057 candidate pairs:')
print('  orcid-match:              ', n(lambda o,m,c: o=='orcid-match'))
print('  orcid-mismatch:           ', n(lambda o,m,c: o=='orcid-mismatch'))
print('  orcid-absent:             ', n(lambda o,m,c: o=='orcid-absent'))
print('cross-check vs coauth>=1:')
print('  orcid-match  & coauth>=1: ', n(lambda o,m,c: o=='orcid-match' and c))
print('  orcid-match  & coauth=0:  ', n(lambda o,m,c: o=='orcid-match' and not c), ' <- ORCID rescues these')
print('  orcid-MISMATCH & coauth>=1:', n(lambda o,m,c: o=='orcid-mismatch' and c), ' <- conflicts, inspect')
print('  absent, oa-id match:      ', n(lambda o,m,c: o=='orcid-absent' and m))
print('  absent, oa-id match, co=0:', n(lambda o,m,c: o=='orcid-absent' and m and not c))
print('  no signal at all:         ', n(lambda o,m,c: o=='orcid-absent' and not m and not c))

# known positives
POS=[('1709150','2134745139'),('1709150','2265974062'),('1709150','2295730369'),
     ('2134745139','2265974062'),('2134745139','2295730369'),('2265974062','2295730369'),
     ('1775477','2285325820'),('2155665017','2303402046')]
print('\nknown positives:')
for a,b in POS:
    p=next((r for r in rows if {r['a'],r['b']}=={a,b}),None)
    print(f"  {a}/{b}: {p['orcid'] if p else '??'}, oa_match={p['oa_id_match'] if p else '?'}")

# conflicts detail
print('\nconflict pairs (coauth>=1 but orcid-mismatch):')
for r in rows:
    if r['orcid']=='orcid-mismatch' and r['coauthors_shared']>=1:
        print(f"  {r['names'][0]} ({r['a']}) vs {r['names'][1]} ({r['b']})  co={r['coauthors_shared']} orcids A={sorted(orc[r['a']])} B={sorted(orc[r['b']])}")


# ============ stage: merge_build ============
import json
from collections import defaultdict
P=json.load(open('profiles.json')); R=json.load(open('scored.json'))

acc=[]; block=set()
for r in R:
    key=(r['a'],r['b'])
    if r['orcid']=='orcid-mismatch': block.add(key); continue
    if r['same_paper']: continue
    if r['orcid']=='orcid-match' or r['coauthors_shared']>=1 or r['oa_id_match']:
        acc.append(r)

par={}
def find(x):
    par.setdefault(x,x)
    while par[x]!=x: par[x]=par[par[x]]; x=par[x]
    return x
def union(a,b): par[find(a)]=find(b)
for r in acc: union(r['a'],r['b'])
cl=defaultdict(set)
for x in list(par): cl[find(x)].add(x)

# clusters containing an internal orcid-mismatch pair -> review, not merged
tainted=set()
for a,b in block:
    if a in par and b in par and find(a)==find(b):
        tainted.add(find(a))
clean=[v for k,v in cl.items() if k not in tainted]
rev  =[v for k,v in cl.items() if k in tainted]

entries=[]
for c in clean:
    ids=sorted(c, key=lambda i:-P[i]['n_papers'])
    keep=ids[0]
    ev=[]
    for r in acc:
        if r['a'] in c and r['b'] in c:
            tag='ORCID' if r['orcid']=='orcid-match' else (f"coauth={r['coauthors_shared']}" if r['coauthors_shared']>=1 else 'OpenAlex-author-id')
            ev.append(tag)
    entries.append({'keep':keep,'merge':ids[1:],
        'name':max((n for i in c for n in P[i]['names']), key=len),
        'evidence':f"big-dedupe 2026-08-21: {len(c)} ids, signals {{{', '.join(sorted(set(ev)))}}}; name-compatible, no ORCID mismatch inside"})
json.dump(entries, open('author_merges_generated.json','w'), indent=1)

nosig=[r for r in R if r['orcid']=='orcid-absent' and not r['oa_id_match'] and r['coauthors_shared']==0 and not r['same_paper']]
with open('data/pools/dedupe_review_queue.md','w') as f:
    f.write('# Dedupe review queue\n\n## Clusters blocked by an internal ORCID mismatch\n')
    for c in sorted(rev,key=len,reverse=True):
        f.write('- ' + '; '.join(f"{P[i]['names'][0]} ({i},{P[i]['n_papers']}p)" for i in sorted(c,key=lambda i:-P[i]['n_papers'])) + '\n')
    f.write(f'\n## ORCID-mismatch pairs (blocked, {len(block)})\n(see scored.json)\n')
    f.write(f'\n## No signal at all ({len(nosig)} pairs) - stay split\n')
    bysur=defaultdict(int)
    for r in nosig: bysur[r['surname']]+=1
    f.write(', '.join(f'{s}:{n}' for s,n in sorted(bysur.items(),key=lambda x:-x[1])[:20])+' ...\n')

ids_merged=sum(len(e['merge']) for e in entries)
print(f'accepted pairs: {len(acc)}  -> clusters: {len(cl)} ({len(clean)} clean, {len(rev)} tainted->review)')
print(f'author_merges entries: {len(entries)}, ids retired: {ids_merged}  (5688 -> {5688-ids_merged})')
print(f'blocked by orcid-mismatch: {len(block)} pairs ({sum(1 for r in R if r["orcid"]=="orcid-mismatch" and r["coauthors_shared"]>=1)} would have merged on coauth alone)')
print(f'no-signal leftovers: {len(nosig)} pairs over {len({x for r in nosig for x in (r["a"],r["b"])})} ids')
print('tainted examples:', ['; '.join(P[i]['names'][0] for i in c) for c in rev[:3]])
