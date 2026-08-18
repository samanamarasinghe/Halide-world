#!/usr/bin/env python3
"""Remove the retired-duplicate gate from the site.

Retired duplicates are dropped by the build in favour of their survivor rather than hidden
behind a control, so the payload never carries the same work twice. Every replacement
asserts it matched exactly once, so a file that is not the expected version fails loudly
instead of being half-patched.

    python3 patch_retired.py            # report what would change
    python3 patch_retired.py --apply
"""
import sys

EDITS = [
    ('build_site.py', [
        ("""    own = {}          # s2_id -> [repo, ...] the paper's own artifact""",
         """    n_retired = [0]
    own = {}          # s2_id -> [repo, ...] the paper's own artifact"""),
        ("""        if s2_id in retired:
            entry['tier'] = 'duplicate'
            entry.update(retired[s2_id])
        carry_curation(rec, entry)""",
         """        if s2_id in retired:
            # A retired duplicate is not shown at all: its survivor carries the work, and a
            # page that offers both is offering the same paper twice. The count still gets
            # reported, so the arithmetic from duplicates.json stays checkable.
            n_retired[0] += 1
            continue
        carry_curation(rec, entry)"""),
        ("""        carry_curation(rec, entry)
        out.append(entry)
    return out, anchor_ids""",
         """        carry_curation(rec, entry)
        out.append(entry)
    return out, anchor_ids, n_retired[0]"""),
        ("""        if key in retired:
            entry['tier'] = 'duplicate'
            entry.update(retired[key])
        out.append(entry)""",
         """        if key in retired:
            continue
        out.append(entry)"""),
        ("""    papers, anchor_ids = build_papers(lane_a, anchors_json, dup, artifacts)""",
         """    papers, anchor_ids, n_retired = build_papers(lane_a, anchors_json, dup, artifacts)"""),
        ("""        'papers': sum(1 for p in papers if p.get('tier') != 'duplicate'),
        'papers_retired': sum(1 for p in papers if p.get('tier') == 'duplicate'),
        'doi_only': sum(1 for p in doi_only if p.get('tier') != 'duplicate'),""",
         """        'papers': len(papers),
        'papers_retired': n_retired,
        'doi_only': len(doi_only),"""),
    ]),
    ('index.html', [
        ("""              <button id="btn-retired" type="button" class="btn" aria-pressed="false" title="Records retired as duplicates of another record: an ACM twin, a preprint alongside its published version, or the same work under two identifiers. They are retired rather than deleted so the merge stays auditable.">Include retired duplicates</button>\n""",
         ""),
    ]),
    ('assets/js/halide-index.js', [
        ("""    if (rec.tier === 'duplicate') return state.retired;\n""", ""),
        ("""    retired: false,\n""", ""),
        ("""  var TIER_LABELS = {
    bundle: 'Vendored bundle', duplicate: 'Retired duplicate', doi_only: 'DOI only',
    dropped: 'Dropped by cleanup'
  };""",
         """  /* Retired duplicates are not in the payload at all — the build drops them in favour of
     their survivor, so there is no tier for them here. */
  var TIER_LABELS = {
    bundle: 'Vendored bundle', doi_only: 'DOI only', dropped: 'Dropped by cleanup'
  };"""),
        ("""      var cls = rec.tier === 'duplicate' || rec.tier === 'dropped' ? 'badge-dup'
        : rec.tier === 'doi_only' ? 'badge-doionly' : 'badge-tail';""",
         """      var cls = rec.tier === 'dropped' ? 'badge-dup'
        : rec.tier === 'doi_only' ? 'badge-doionly' : 'badge-tail';"""),
        ("""    if (rec.tier === 'duplicate' && rec.survivor) {
      var dup = el('div', 'pub-evidence');
      dup.appendChild(el('span', 'edge-label', 'Retired in favour of'));
      edgeLink(dup, rec.survivor, rec.survivor, null);
      dup.appendChild(el('span', 'edge-more', '(' + prettify(rec.dup_kind) + ')'));
      li.appendChild(dup);
    }\n""", ""),
        ("""    $('btn-retired').onclick = function () {
      state.retired = !state.retired;
      this.setAttribute('aria-pressed', state.retired ? 'true' : 'false');
      buildViewToggles();
      applyFilters();
    };\n""", ""),
    ]),
    ('assets/css/style.css', [
        (""".pub-item.tier-duplicate, .pub-item.tier-dropped { background: #fdf8f8; }""",
         """.pub-item.tier-dropped { background: #fdf8f8; }"""),
    ]),
    ('tests/site_smoke.js', [
        ("""  console.log('retired duplicates');
  $('btn-retired').click();
  await settle();
  [...q('.view-btn')].find((b) => b.textContent.startsWith('Papers')).click();
  await settle();
  check('retired duplicates appear', q('.pub-item.tier-duplicate').length >= 0);""",
         """  console.log('retired duplicates are gone, not gated');
  check('no retired-duplicate control', !$('btn-retired'));
  check('no retired-duplicate records', q('.pub-item.tier-duplicate').length === 0);"""),
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
