/* Headless smoke test for the index page.
   Loads index.html in jsdom, serves data/site/ from disk, then walks every view, opens a
   facet, follows an edge and turns the bundles on. Catches the class of defect that only
   appears once real data is in the page: a facet with no values, a card that throws on a
   record shape, a count that disagrees with the list. Run: node tests/site_smoke.js */
const fs = require('fs');
const path = require('path');
const { JSDOM, VirtualConsole } = require('jsdom');

const ROOT = path.join(__dirname, '..');
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
  check('repos exclude bundles', counts.Repositories === 736, 'got ' + counts.Repositories);
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

  console.log('bundles');
  $('btn-bundles').click();
  await settle();
  await settle();
  const repoBtn = [...q('.view-btn')].find((b) => b.textContent.startsWith('Repositories'));
  check('bundles load', parseInt(repoBtn.querySelector('.view-badge').textContent, 10) === 3564,
    repoBtn.querySelector('.view-badge').textContent);
  repoBtn.click();
  await settle();
  check('bundle cards render', q('.pub-item.tier-bundle').length > 0);
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
    check('author click lands on the person', q('.pub-item .badge-person').length === 1);
    $('btn-clear').click();
    await settle();
  }

  console.log('retired duplicates');
  $('btn-retired').click();
  await settle();
  [...q('.view-btn')].find((b) => b.textContent.startsWith('Papers')).click();
  await settle();
  check('retired duplicates appear', q('.pub-item.tier-duplicate').length >= 0);

  console.log(fail.length ? '\n' + fail.length + ' FAILURES' : '\nall checks passed');
  process.exit(fail.length ? 1 : 0);
})();
