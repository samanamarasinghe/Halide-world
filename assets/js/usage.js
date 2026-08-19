/* Usage tracking for the Halide index. Umami, cookieless, loaded from index.html.

   WHY THIS IS A SEPARATE FILE AND NOT AN EDIT TO halide-index.js:
   the index script belongs to the site lane and is rewritten often. Event delegation on
   the document reads the same clicks without touching it, so tracking survives a rewrite
   of the page and a rewrite of the page cannot be broken by tracking. The cost is that
   this reads the DOM rather than the page's internal state, which is why every selector
   below is checked before use and every read is wrapped.

   Pageviews alone say almost nothing here: this is ONE page, so a visit is a single hit
   and everything a reader actually does happens after it. Hence four custom events.

     view     the reader switched between Papers / Repositories / People
     search   a query was typed (debounced -- "h", "ha", "hal" are not three searches)
     facet    a filter value was turned ON (turning one off is not an intent signal)
     open     a record was opened, the closest thing this page has to a click-through

   SEND_QUERIES sends the reader's typed text. It is the most useful signal an index like
   this has, and it is also the only visitor-entered text that leaves the page. Set it to
   false to keep the event and drop the words. */
(function () {
  'use strict';

  var SEND_QUERIES = true;
  var DEBOUNCE_MS = 900;

  function track(name, props) {
    try {
      if (window.umami && typeof window.umami.track === 'function') {
        window.umami.track(name, props || {});
      }
    } catch (e) { /* tracking must never take the page down */ }
  }

  function activeView() {
    try {
      var btn = document.querySelector('.view-btn.active');
      if (!btn) return 'unknown';
      /* The label carries a count badge; the first text node is the name alone. */
      return (btn.firstChild && btn.firstChild.nodeValue || btn.textContent || '')
        .trim().toLowerCase() || 'unknown';
    } catch (e) { return 'unknown'; }
  }

  function resultCount() {
    /* The header reads "(123)" or "(123 of 456)". The first number is what is showing. */
    try {
      var node = document.getElementById('pubs-count');
      var m = node && /(\d+)/.exec(node.textContent || '');
      return m ? parseInt(m[1], 10) : null;
    } catch (e) { return null; }
  }

  document.addEventListener('DOMContentLoaded', function () {
    var input = document.getElementById('facet-text');
    var timer = null;

    if (input) {
      input.addEventListener('input', function () {
        if (timer) clearTimeout(timer);
        timer = setTimeout(function () {
          var q = (input.value || '').replace(/\s+/g, ' ').trim();
          if (!q) return;
          var props = { view: activeView(), length: q.length };
          var n = resultCount();
          if (n !== null) props.results = n;
          if (SEND_QUERIES) props.query = q.slice(0, 100).toLowerCase();
          track('search', props);
        }, DEBOUNCE_MS);
      });
    }

    /* One delegated listener rather than per-element handlers: the page rebuilds its
       facet controls on every filter change, so anything bound to an element is gone the
       moment a reader clicks something. */
    document.addEventListener('click', function (ev) {
      try {
        var t = ev.target;
        if (!t || !t.closest) return;

        var view = t.closest('.view-btn');
        if (view && !view.classList.contains('active')) {
          var label = (view.firstChild && view.firstChild.nodeValue || '').trim();
          track('view', { view: label.toLowerCase(), from: activeView() });
          return;
        }

        /* Facet buttons carry a count badge; the first text node is the value. Only an
           ON click is recorded -- deselecting says nothing about what a reader wants. */
        var chip = t.closest('.year-btn');
        if (chip && !chip.disabled && !chip.classList.contains('active')) {
          track('facet', {
            value: (chip.firstChild && chip.firstChild.nodeValue || '').trim().slice(0, 60),
            view: activeView()
          });
          return;
        }

        var action = t.closest('.pub-action');
        if (action) {
          track('open', {
            action: (action.textContent || '').trim().slice(0, 40),
            view: activeView()
          });
        }
      } catch (e) { /* never interfere with the click itself */ }
    }, true);

    /* Facet checkboxes are labels, not buttons, so they arrive as a change event. */
    document.addEventListener('change', function (ev) {
      try {
        var cb = ev.target;
        if (!cb || cb.type !== 'checkbox' || !cb.checked) return;
        if (!cb.closest || !cb.closest('.facet-item')) return;
        track('facet', { value: String(cb.value || '').slice(0, 60), view: activeView() });
      } catch (e) { /* as above */ }
    }, true);
  });
})();
