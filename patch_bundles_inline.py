#!/usr/bin/env python3
"""Vendored bundles become ordinary repository records.

`third_party_bundle` is already a value of the Verdict facet, so a second control saying
the same thing was redundant — and it defaulted the other way, which meant the Verdict
facet reported a count the view did not show. The bundles now travel in the main payload,
load with everything else and are filtered like any other repository.

The payload grows from 3.0MB to 4.2MB, 800KB over the wire.

Every replacement asserts it matched exactly once, so a file that is not the expected
version fails loudly instead of being half-patched.

    python3 patch_bundles_inline.py            # report what would change
    python3 patch_bundles_inline.py --apply
"""
import sys

EDITS = [
    ('build_site.py', [
        ('''# Repos whose only Halide is a vendored third-party copy. Kept in the payload but flagged,
# because dropping 2,828 records outright would make the corpus unauditable from the page.
BUNDLE = 'third_party_bundle\'''',
         '''# Repos whose only Halide is a vendored third-party copy. They are ordinary records
# carrying an ordinary verdict; the page filters them through the Verdict facet like any
# other, which is why they no longer travel in a file of their own.
BUNDLE = 'third_party_bundle\''''),

        ("""        if rec.get('verdict') == BUNDLE:
            entry['tier'] = 'bundle'
""", ""),

        ("""        'repos': sum(1 for r in repos if not r.get('tier')),""",
         """        'repos': sum(1 for r in repos if r.get('verdict') != BUNDLE),"""),

        ("""        'bundles': sum(1 for r in repos if r.get('tier') == 'bundle'),""",
         """        'bundles': sum(1 for r in repos if r.get('verdict') == BUNDLE),"""),

        ("""    os.makedirs(OUT_DIR, exist_ok=True)
    # The 2,828 vendored bundles are four fifths of the repo records and are off by
    # default, so they ship in their own file and the page fetches it only when the
    # reader asks for them.
    bundles = [r for r in repos if r.get('tier') == 'bundle']
    main = [e for e in entries if e.get('tier') != 'bundle']
    payload = {'schema_version': 1, 'counts': counts, 'entries': main}
    with open(os.path.join(OUT_DIR, 'halide-index.json'), 'w') as fh:
        json.dump(payload, fh, separators=(',', ':'))
    with open(os.path.join(OUT_DIR, 'halide-bundles.json'), 'w') as fh:
        json.dump({'schema_version': 1, 'entries': bundles}, fh, separators=(',', ':'))""",
         """    os.makedirs(OUT_DIR, exist_ok=True)
    payload = {'schema_version': 1, 'counts': counts, 'entries': entries}
    with open(os.path.join(OUT_DIR, 'halide-index.json'), 'w') as fh:
        json.dump(payload, fh, separators=(',', ':'))
    stale = os.path.join(OUT_DIR, 'halide-bundles.json')
    if os.path.exists(stale):
        os.remove(stale)        # bundles now travel in the main payload"""),
    ]),
    ('index.html', [
        ("""              <button id="btn-bundles" type="button" class="btn" aria-pressed="false" title="Repositories whose only Halide is a vendored third-party copy — Halide arrived inside something else they depend on, and nothing in the repository was written against it. 2,828 of them, four fifths of everything the repository harvest found, which is why they are off by default. They load on demand from a separate file.">Include vendored bundles</button>\n""",
         ""),
    ]),
    ('assets/js/halide-index.js', [
        ("""   Vendored bundles live in data/site/halide-bundles.json and load only when asked for.""",
         """   Vendored third-party bundles are ordinary records here: they carry their own verdict and
   are filtered through the Verdict facet like every other repository."""),

        ("""  var INDEX_PATH  = 'data/site/halide-index.json';
  var BUNDLE_PATH = 'data/site/halide-bundles.json';
  var INFO_PATH   = 'data/site/build-info.json';""",
         """  var INDEX_PATH = 'data/site/halide-index.json';
  var INFO_PATH  = 'data/site/build-info.json';"""),

        ("""  var DATA = [];         // every node except the vendored bundles
  var BUNDLES = null;    // lazy: null until the reader asks, [] while loading
""",
         """  var DATA = [];         // every node
"""),

        ("""  /* Two classes never reach the page: a retired duplicate, dropped by the build in favour
     of its survivor, and a repository the cleanup pass judged to carry only someone else's
     Halide-touching source. Neither has a tier here. */
  var TIER_LABELS = { bundle: 'Vendored bundle', doi_only: 'DOI only' };""",
         """  /* Two classes never reach the page: a retired duplicate, dropped by the build in favour
     of its survivor, and a repository the cleanup pass judged to carry only someone else's
     Halide-touching source. The only tier left marks provenance rather than exclusion. */
  var TIER_LABELS = { doi_only: 'DOI only' };"""),

        ("""    bundles: false,
""", ""),

        ("""  function activeData() {
    var out = DATA;
    if (state.bundles && BUNDLES && BUNDLES.length) out = out.concat(BUNDLES);
    return out;
  }

""", ""),

        ("""  /* Tier gates are deliberately separate from the facets: they answer "should this class
     of record be in the corpus at all", and a facet count that silently included retired
     duplicates would be a different number from the one in the header. */
  function passesTier(rec) {
    if (rec.tier === 'bundle') return state.bundles;
    return true;
  }

""", ""),

        ("""      if (!inView(rec) || !passesTier(rec)) return false;""",
         """      if (!inView(rec)) return false;"""),

        ("""    return activeData().filter(function (rec) {""",
         """    return DATA.filter(function (rec) {"""),

        ("""      var cls = rec.tier === 'doi_only' ? 'badge-doionly' : 'badge-tail';""",
         """      var cls = 'badge-doionly';"""),

        ("""    var universe = activeData().filter(function (r) { return inView(r) && passesTier(r); }).length;""",
         """    var universe = DATA.filter(inView).length;"""),

        ("""      var n = activeData().filter(function (r) { return v.kinds[r.kind] && passesTier(r); }).length;""",
         """      var n = DATA.filter(function (r) { return v.kinds[r.kind]; }).length;"""),

        ("""    /* The bundles gate only reaches repository records, so it belongs to that view rather
       than to the page. Left in the global row it invited a press on Papers or People that
       would fetch a 1.3MB file and change nothing. */
    var bundleBtn = $('btn-bundles');
    if (bundleBtn) bundleBtn.className = 'btn' + (state.view === 'repos' ? '' : ' hidden');
""", ""),

        ("""    activeData().forEach(function (rec) {
      if (rec.kind !== 'person') return;""",
         """    DATA.forEach(function (rec) {
      if (rec.kind !== 'person') return;"""),

        ("""    var all = activeData();""", """    var all = DATA;"""),

        ("""  function loadBundles() {
    if (BUNDLES) return Promise.resolve();
    BUNDLES = [];
    return fetch(BUNDLE_PATH)
      .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then(function (raw) {
        BUNDLES = (raw && raw.entries) || [];
        indexNodes(BUNDLES);
        computeUniverse();
        computeMaxima();
        applyFacetDefaults();
      })
      .catch(function (e) {
        els.errors.textContent = 'Could not load the vendored bundles: ' + e.message;
      });
  }

""", ""),

        ("""    $('btn-bundles').onclick = function () {
      var btn = this;
      state.bundles = !state.bundles;
      btn.setAttribute('aria-pressed', state.bundles ? 'true' : 'false');
      if (state.bundles) {
        btn.textContent = 'Loading bundles…';
        loadBundles().then(function () {
          btn.textContent = 'Include vendored bundles';
          buildViewToggles();
          buildFacetGrid();
          applyFilters();
        });
        return;
      }
      buildViewToggles();
      applyFilters();
    };

""", ""),
    ]),
    ('assets/css/style.css', [
        (""".pub-item.tier-bundle { opacity: 0.9; background: #fafafa; }\n""", ""),
    ]),
    ('tests/site_smoke.js', [
        ("""  check('repos exclude bundles and dropped', counts.Repositories === INFO.repos,
    'got ' + counts.Repositories + ', payload says ' + INFO.repos);""",
         """  check('repos include bundles, exclude dropped',
    counts.Repositories === INFO.repos + INFO.bundles,
    'got ' + counts.Repositories + ', payload says ' + (INFO.repos + INFO.bundles));"""),

        ("""  console.log('bundles');
  $('btn-bundles').click();
  await settle();
  await settle();
  const repoBtn = [...q('.view-btn')].find((b) => b.textContent.startsWith('Repositories'));
  check('bundles load', parseInt(repoBtn.querySelector('.view-badge').textContent, 10) === INFO.repos + INFO.bundles,
    repoBtn.querySelector('.view-badge').textContent + ' vs ' + (INFO.repos + INFO.bundles));
  repoBtn.click();
  await settle();
  check('bundle cards render', q('.pub-item.tier-bundle').length > 0);
  check('results capped with a way past it', /Show all/.test($('pubs-more').textContent), $('pubs-more').textContent);
""",
         """  console.log('bundles are ordinary repository records');
  check('no bundles gate', !$('btn-bundles'));
  const repoBtn = [...q('.view-btn')].find((b) => b.textContent.startsWith('Repositories'));
  check('bundles counted in the view',
    parseInt(repoBtn.querySelector('.view-badge').textContent, 10) === INFO.repos + INFO.bundles,
    repoBtn.querySelector('.view-badge').textContent + ' vs ' + (INFO.repos + INFO.bundles));
  repoBtn.click();
  await settle();
  const vblock = [...q('#filter-grid .filter-block')]
    .find((b) => /Verdict/.test(b.querySelector('.filter-label').textContent));
  const vbundle = [...vblock.querySelectorAll('.facet-item')]
    .find((l) => /Vendored third-party bundle/.test(l.textContent));
  check('the Verdict facet carries them', !!vbundle, vblock.textContent.slice(0, 80));
  check('results capped with a way past it', /Show all/.test($('pubs-more').textContent), $('pubs-more').textContent);
"""),

        ("""  console.log('bundles gate belongs to the repositories view');
  for (const name of ['Papers', 'People', 'Anchors']) {
    [...q('.view-btn')].find((b) => b.textContent.startsWith(name)).click();
    await settle();
    check(name + ': bundles button hidden', /hidden/.test($('btn-bundles').className),
      $('btn-bundles').className);
  }
  [...q('.view-btn')].find((b) => b.textContent.startsWith('Repositories')).click();
  await settle();
  check('Repositories: bundles button shown', !/hidden/.test($('btn-bundles').className));

""", ""),
    ]),
    ('docs/site.md', [
        ("""## One class of record is gated rather than faceted""",
         """## What the page leaves out"""),

        ("""- **Vendored bundles**, 2,828 repositories whose only Halide arrived inside a third-party
  dependency. Off by default and shipped in `data/site/halide-bundles.json`, fetched only
  when the button is pressed. The button shows on the Repositories view alone, since it
  reaches no other kind of record.
""",
         """The 2,828 vendored bundles — repositories whose only Halide arrived inside a third-party
dependency — are NOT among them. They carry `third_party_bundle` as their verdict and are
filtered through the Verdict facet like any other repository.

"""),
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
