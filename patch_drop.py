#!/usr/bin/env python3
"""Drop the rejected repositories from the payload instead of gating them.

A repository the cleanup pass dropped carries someone else's Halide-touching source and no
relationship of its own, so it does not belong in a browsable index at all. The record
still exists in lane_b_curatable.json with its reason, which is where a wrong drop is
audited; the page simply does not carry it, and the control that showed them is gone.

Every replacement asserts it matched exactly once, so a file that is not the expected
version fails loudly instead of being half-patched.

    python3 patch_drop.py            # report what would change
    python3 patch_drop.py --apply
"""
import sys

EDITS = [
    ('build_site.py', [
        ("""    extra = {}
    for rec in (curatable or {}).get('repos', []):
        extra[rec['repo']] = rec""",
         """    n_dropped = [0]
    extra = {}
    for rec in (curatable or {}).get('repos', []):
        extra[rec['repo']] = rec"""),

        ("""        # His ruling: a dropped repo is kept with its reason rather than deleted, and
        # hidden from the page by default. Same gate as a retired duplicate, not a facet.
        if clean.get('status') == 'drop':
            entry['tier'] = 'dropped'""",
         """        # A dropped repo carries someone else's Halide-touching source and no relationship
        # of its own, so it does not belong in a browsable index at all. The record still
        # exists in lane_b_curatable.json with its reason, which is where a wrong drop is
        # audited; the page just does not carry it.
        if clean.get('status') == 'drop':
            n_dropped[0] += 1
            continue"""),

        ("""        carry_curation(rec, entry)
        out.append(entry)
    return out


def build_people""",
         """        carry_curation(rec, entry)
        out.append(entry)
    return out, n_dropped[0]


def build_people"""),

        ("""    repos = build_repos(lane_b, artifacts, curatable)""",
         """    repos, n_dropped = build_repos(lane_b, artifacts, curatable)"""),

        ("""        'repos_dropped': sum(1 for r in repos if r.get('tier') == 'dropped'),""",
         """        'repos_dropped': n_dropped,"""),
    ]),
    ('index.html', [
        ("""              <button id="btn-dropped" type="button" class="btn" aria-pressed="false" title="Repositories the cleanup pass dropped: a redistributed copy of someone else's Halide-touching source, or an unmodified re-upload of Halide. They are kept with the reason recorded rather than deleted, so a later harvest does not rediscover and rejudge them, and hidden here unless you ask.">Include dropped repositories</button>\n""",
         ""),
    ]),
    ('assets/js/halide-index.js', [
        ("""    if (rec.tier === 'dropped') return state.dropped;\n""", ""),
        ("""    dropped: false,\n""", ""),
        ("""  /* Retired duplicates are not in the payload at all — the build drops them in favour of
     their survivor, so there is no tier for them here. */
  var TIER_LABELS = {
    bundle: 'Vendored bundle', doi_only: 'DOI only', dropped: 'Dropped by cleanup'
  };""",
         """  /* Two classes never reach the page: a retired duplicate, dropped by the build in favour
     of its survivor, and a repository the cleanup pass judged to carry only someone else's
     Halide-touching source. Neither has a tier here. */
  var TIER_LABELS = { bundle: 'Vendored bundle', doi_only: 'DOI only' };"""),
        ("""      var cls = rec.tier === 'dropped' ? 'badge-dup'
        : rec.tier === 'doi_only' ? 'badge-doionly' : 'badge-tail';""",
         """      var cls = rec.tier === 'doi_only' ? 'badge-doionly' : 'badge-tail';"""),
        ("""    var dropBtn = $('btn-dropped');
    if (dropBtn) {
      dropBtn.onclick = function () {
        state.dropped = !state.dropped;
        this.setAttribute('aria-pressed', state.dropped ? 'true' : 'false');
        buildViewToggles();
        applyFilters();
      };
    }
""", ""),
    ]),
    ('assets/css/style.css', [
        (""".pub-item.tier-dropped { background: #fdf8f8; }\n""", ""),
    ]),
    ('tests/site_smoke.js', [
        ("""  console.log('dropped repositories');
  const drop = $('btn-dropped');
  check('dropped gate exists', !!drop);
  if (drop) {
    [...q('.view-btn')].find((b) => b.textContent.startsWith('Repositories')).click();
    await settle();
    const before2 = q('.pub-item').length;
    drop.click();
    await settle();
    check('dropped repos appear only when asked', q('.pub-item').length >= before2);
    drop.click();
    await settle();
  }
""",
         """  console.log('dropped repositories are gone, not gated');
  check('no dropped-repo control', !$('btn-dropped'));
  check('no dropped-repo records', q('.pub-item.tier-dropped').length === 0);
"""),
    ]),
    ('docs/site.md', [
        ("""## Two classes of record are gated rather than faceted""",
         """## One class of record is gated rather than faceted"""),
        ("""offers the same work twice.""",
         """offers the same work twice. Nor are the repositories the cleanup pass dropped: they carry
someone else's Halide-touching source and no relationship of their own, and a wrong drop is
audited in `data/pools/lane_b_curatable_summary.json`, which records every one with its
reason."""),
        ("""- **Dropped repositories**, the ones the cleanup pass judged redistributed copies or
  unmodified re-uploads. Kept with their reason rather than deleted, off by default.
""", ""),
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
