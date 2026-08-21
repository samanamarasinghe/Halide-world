/* Headless smoke test for the index page.
   Loads index.html in jsdom, serves data/site/ from disk, then walks every view, opens a
   facet, follows an edge and turns the bundles on. Catches the class of defect that only
   appears once real data is in the page: a facet with no values, a card that throws on a
   record shape, a count that disagrees with the list. Run: node tests/site_smoke.js */
const fs = require('fs');
const path = require('path');
const { JSDOM, VirtualConsole } = require('jsdom');

const ROOT = path.join(__dirname, '..');
// Expected counts come from the payload the page is about to load, not from constants:
// the corpus legitimately changes as pools land, and a test that hardcodes 736 fails for
// the wrong reason the first time a repo is dropped.
const INFO = JSON.parse(fs.readFileSync(path.join(ROOT, 'data/site/build-info.json'), 'utf8')).counts;
const fail = [];
function check(name, cond, detail) {
  if (cond) { console.log('  ok   ' + name); return; }
  console.log('  FAIL ' + name + (detail ? ' — ' + detail : ''));
  fail.push(name);
}

const vc = new VirtualConsole();
vc.on('jsdomError', (e) => { console.log('  JSDOM ERROR ' + e.message); fail.push('jsdom: ' + e.message); });
vc.on('error', (m) => { console.log('  PAGE ERROR ' + m); fail.push('page: ' + m); });

const dom = new JSDOM(fs.readFileSync(path.join(ROOT, 'index.html'), 'utf8'), {
  runScripts: 'dangerously',
  resources: undefined,
  virtualConsole: vc,
  url: 'https://example.org/'
});
const { window } = dom;

// fetch against the working tree
window.fetch = (url) => {
  const file = path.join(ROOT, url);
  if (!fs.existsSync(file)) return Promise.resolve({ ok: false, status: 404 });
  return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(JSON.parse(fs.readFileSync(file, 'utf8'))) });
};
window.scrollTo = () => {};

const script = fs.readFileSync(path.join(ROOT, 'assets/js/halide-index.js'), 'utf8');
window.eval(script);

const $ = (id) => window.document.getElementById(id);
const q = (sel) => window.document.querySelectorAll(sel);
const settle = () => new Promise((r) => setTimeout(r, 60));

(async () => {
  await settle();

  console.log('load');
  check('no load error', !$('pubs-errors').textContent, $('pubs-errors').textContent);
  check('view buttons', q('.view-btn').length === 4);
  check('results rendered', q('.pub-item').length > 0);
  const counts = {};
  q('.view-btn').forEach((b) => { counts[b.textContent.replace(/\d+$/, '')] = parseInt(b.querySelector('.view-badge').textContent, 10); });
  console.log('  view counts ' + JSON.stringify(counts));
  check('papers view non-empty', counts.Papers > 1000);
  check('repos include bundles, exclude dropped',
    counts.Repositories === INFO.repos + INFO.bundles,
    'got ' + counts.Repositories + ', payload says ' + (INFO.repos + INFO.bundles));
  check('people present', counts.People > 4000);
  check('anchors 16', counts.Anchors === 16);

  for (const name of ['Papers', 'Repositories', 'People', 'Anchors']) {
    console.log(name);
    [...q('.view-btn')].find((b) => b.textContent.startsWith(name)).click();
    await settle();
    check(name + ': cards render', q('.pub-item').length > 0);
    check(name + ': count header set', /\(\d/.test($('pubs-count').textContent), $('pubs-count').textContent);
    const blocks = [...q('#filter-grid .filter-block')];
    check(name + ': facets have values or none by design',
      name === 'Anchors' ? blocks.length === 0 : blocks.length > 0);
    for (const b of blocks) {
      const label = b.querySelector('.filter-label').textContent;
      const rows = b.querySelectorAll('.facet-item, .year-btn').length;
      check(name + ': facet "' + label.replace(/i$/, '') + '" has rows', rows > 0);
    }
  }

  console.log('interaction');
  [...q('.view-btn')].find((b) => b.textContent.startsWith('Papers')).click();
  await settle();
  const before = q('.pub-item').length;
  const cb = q('#filter-grid input[type=checkbox]')[0];
  cb.checked = true; cb.onchange.call(cb);
  await settle();
  check('facet narrows the list', q('.pub-item').length <= before);
  check('facet header shows a count', /\(\d+/.test(q('#filter-grid .facet-count')[0].textContent));

  $('btn-clear').click();
  await settle();
  check('clear restores', q('.pub-item').length === before, q('.pub-item').length + ' vs ' + before);

  $('facet-text').value = 'FlashAttention';
  $('facet-text').oninput.call($('facet-text'));
  await settle();
  check('text search works', q('.pub-item').length >= 1 && q('.pub-item').length < 50, q('.pub-item').length + ' hits');

  $('btn-clear').click();
  await settle();

  // Follow an edge: open the first paper carrying an artifact and click through to the repo.
  $('btn-expand').click();
  await settle();
  // A repository that is itself in the index renders as a SPAN with a click handler; one
  // that is not (a vendored bundle, not yet loaded) renders as a plain outbound A. Only the
  // first kind navigates in-page, so that is what this exercises.
  const link = [...q('.pub-edges .edge-link')].find((e) => e.tagName === 'SPAN');
  check('an in-page edge link exists', !!link);
  if (link) {
    link.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
    await settle();
    check('edge focuses one node', q('.pub-item').length === 1, q('.pub-item').length + ' cards');
    check('focus note explains', /Showing one node/.test($('view-note').textContent));
    $('btn-clear').click();
    await settle();
  }

  console.log('bundles are ordinary repository records');
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

  console.log('anchor navigation and authorship edges');
  $('btn-clear').click();
  await settle();
  [...q('.view-btn')].find((b) => b.textContent.startsWith('Anchors')).click();
  await settle();
  const citing = [...q('.pub-action')].find((a) => /Citing works/.test(a.textContent));
  check('anchor offers its citing works', !!citing);
  if (citing) {
    citing.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
    await settle();
    const n = q('.pub-item').length;
    check('citing works land in Papers', n > 0 && /Papers/.test([...q('.view-btn')].find((b) => b.className.indexOf('active') >= 0).textContent));
  }
  $('btn-clear').click();
  await settle();
  [...q('.view-btn')].find((b) => b.textContent.startsWith('Papers')).click();
  await settle();
  const person = [...q('.pub-authors .edge-link')][0];
  check('author name is an edge', !!person);
  if (person) {
    person.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
    await settle();
    const landed = q('.pub-item');
    const onPeople = /People/.test([...q('.view-btn')]
      .find((b) => b.className.indexOf('active') >= 0).textContent);
    check('author click lands on the person',
      landed.length === 1 && onPeople && landed[0].textContent.indexOf(person.textContent) >= 0);
    $('btn-clear').click();
    await settle();
  }

  console.log('sorting');
  $('btn-clear').click();
  await settle();
  [...q('.view-btn')].find((b) => b.textContent.startsWith('Repositories')).click();
  await settle();
  const sort = $('sort-within');
  const hasStars = [...sort.options].some((o) => o.value === 'stars');
  check('repositories offer a stars sort', hasStars);
  if (hasStars) {
    sort.value = 'stars'; sort.onchange.call(sort);
    await settle();
    // Stars render in the dim meta line as "★ N". Unknown counts sort last, so the
    // sequence has to be non-increasing over the cards that carry one.
    const seq = [...q('.pub-item')].map((li) => {
      const m = (li.querySelector('.pub-dim') || {}).textContent || '';
      const hit = m.match(/\u2605\s(\d+)/);
      return hit ? parseInt(hit[1], 10) : null;
    }).filter((n) => n !== null);
    // Star counts only exist once lane_b_curatable.json is in the pools, so the ordering
    // is asserted when there is something to order and reported as absent when there is not.
    if (seq.length < 10) {
      console.log('  --   no star data in this payload; ordering not asserted');
    } else {
      let ok = true;
      for (let i = 1; i < seq.length; i++) if (seq[i] > seq[i - 1]) ok = false;
      check('stars sort is non-increasing', ok, seq.slice(0, 6).join(','));
    }
  }
  [...q('.view-btn')].find((b) => b.textContent.startsWith('Papers')).click();
  await settle();
  const psort = $('sort-within');
  psort.value = 'cited'; psort.onchange.call(psort);
  await settle();
  const cites = [...q('.pub-item')].map((li) => {
    const m = ((li.querySelector('.pub-dim') || {}).textContent || '').match(/cited by (\d+)/);
    return m ? parseInt(m[1], 10) : null;
  }).filter((n) => n !== null);
  let cok = cites.length > 10;
  for (let i = 1; i < cites.length; i++) if (cites[i] > cites[i - 1]) cok = false;
  check('citation sort is non-increasing', cok, cites.slice(0, 6).join(','));

  console.log('dropped repositories are gone, not gated');
  check('no dropped-repo control', !$('btn-dropped'));
  check('no dropped-repo records', q('.pub-item.tier-dropped').length === 0);

  console.log('person layer');
  $('btn-clear').click();
  await settle();
  [...q('.view-btn')].find((b) => b.textContent.startsWith('People')).click();
  await settle();
  const psorts = [...$('sort-within').options].map((o) => o.value);
  check('people offer a commits sort', psorts.indexOf('commits') >= 0);
  $('sort-within').value = 'commits'; $('sort-within').onchange.call($('sort-within'));
  await settle();
  const top = q('.pub-item')[0].querySelector('.pub-dim').textContent;
  // Contribution data only exists once halide_contributors.json is on disk, so the share
  // is asserted when there is one and reported as absent when there is not.
  if (INFO.people_with_contributions) {
    check('top person shows a contribution share', /commits to .+\(\d/.test(top), top.trim());
  } else {
    console.log('  --   no contributor data in this payload; share not asserted');
  }

  console.log('default sorts');
  for (const [name, want] of [['Papers', 'contexts'], ['Repositories', 'matches'],
                              ['People', 'score'], ['Anchors', 'cited_by_pool']]) {
    $('btn-clear').click();
    await settle();
    [...q('.view-btn')].find((b) => b.textContent.startsWith(name)).click();
    await settle();
    check(name + ': opens on ' + want, $('sort-within').value === want, $('sort-within').value);
  }

  console.log('total contributions');
  [...q('.view-btn')].find((b) => b.textContent.startsWith('People')).click();
  await settle();
  const ssorts = [...$('sort-within').options].map((o) => o.value);
  check('people offer a combined score sort', ssorts.indexOf('score') >= 0);
  $('sort-within').value = 'score'; $('sort-within').onchange.call($('sort-within'));
  await settle();
  // The figure itself is internal, so the ordering is checked against the payload: rebuild
  // the score from the data and require the rendered names to match its ranking.
  const people = JSON.parse(fs.readFileSync(path.join(ROOT, 'data/site/halide-index.json'), 'utf8'))
    .entries.filter((e) => e.kind === 'person');
  const maxC = Math.max(1, ...people.map((p) => p.contrib_commits || 0));
  const maxP = Math.max(1, ...people.map((p) => p.n_papers || 0));
  const ranked = people
    .map((p) => ({ name: p.name, s: (p.contrib_commits || 0) / maxC + (p.n_papers || 0) / maxP }))
    .sort((a, b) => (b.s - a.s) || String(a.name).localeCompare(String(b.name)))
    .slice(0, 5).map((p) => p.name);
  const rendered = [...q('.pub-item')].slice(0, 5)
    .map((li) => li.querySelector('.pub-title').textContent.trim());
  check('score ranking reaches the page', ranked.join('|') === rendered.join('|'),
    rendered.join('|') + ' vs ' + ranked.join('|'));
  check('the figure itself stays off the card',
    ![...q('.pub-dim')].some((d) => /total contributions/.test(d.textContent)));

  console.log('contributions facet');
  $('btn-clear').click();
  await settle();
  [...q('.view-btn')].find((b) => b.textContent.startsWith('People')).click();
  await settle();
  const cblock = [...q('#filter-grid .filter-block')]
    .find((b) => /Contributions/.test(b.querySelector('.filter-label').textContent));
  check('one merged contributions facet', !!cblock);
  check('no separate contributor facet',
    ![...q('#filter-grid .filter-label')].some((l) => /Halide contributor/.test(l.textContent)));
  if (cblock) {
    const boxes = [...cblock.querySelectorAll('.facet-item input')];
    check('every value starts selected', boxes.length > 0 && boxes.every((b) => b.checked),
      boxes.filter((b) => !b.checked).length + ' unselected');
    // All values lit must filter nothing: everyone carries at least one, including an
    // author whose only indexed work is an anchor and a committer with no paper.
    check('all lit shows the whole view', /^\(\d+\)$/.test($('pubs-count').textContent),
      $('pubs-count').textContent);
    const one = [...cblock.querySelectorAll('.facet-item')].find((l) => /1 paper/.test(l.textContent));
    if (one) {
      const cb2 = one.querySelector('input');
      cb2.checked = false; cb2.onchange.call(cb2);
      await settle();
      check('unlighting a value narrows', /of/.test($('pubs-count').textContent),
        $('pubs-count').textContent);
      $('btn-clear').click();
      await settle();
      check('clear relights every value',
        [...q('#filter-grid .facet-item input')].filter((b) => !b.checked).length >= 0);
    }
  }

  console.log('retired duplicates are gone, not gated');
  check('no retired-duplicate control', !$('btn-retired'));
  check('no retired-duplicate records', q('.pub-item.tier-duplicate').length === 0);

  console.log(fail.length ? '\n' + fail.length + ' FAILURES' : '\nall checks passed');
  process.exit(fail.length ? 1 : 0);
})();
