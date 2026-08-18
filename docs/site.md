# The index page

`index.html` at the repository root, published by GitHub Pages from `main`. It is a static
page: no framework, no build tooling, three files and a generated payload.

    index.html                     markup, filter controls, tooltips
    assets/css/style.css           styling, shared shape with SDVworld-index
    assets/js/halide-index.js      the filter/render controller
    build_site.py                  data/pools/ -> data/site/halide-index.json
    tests/site_smoke.js            headless check of the page against the real payload

## Rebuilding

    python3 build_site.py            # report counts, write nothing
    python3 build_site.py --write    # write data/site/halide-index.json and build-info.json
    node tests/site_smoke.js         # needs jsdom: npm install jsdom

`data/site/` is generated. Never hand-edit it — change a pool and rebuild. The page reads
the payload over `fetch`, so opening `index.html` from the filesystem will not work; serve
the directory instead:

    python3 -m http.server 8000     # then open http://localhost:8000/

## What the page shows

Four node views over one filter engine. A view names the node kinds it shows and the
facets that mean something for them; everything else — search, sort, tier gates, the
200-value cap, the result cap — is shared.

| View | Nodes | Facets |
|---|---|---|
| Papers | works citing an anchor | cites anchor, year, venue, citation intent, artifact, field, role\* |
| Repositories | repositories with Halide in them | verdict, evidence, signature, where it sits, paper artifact, cleanup status\*, language\*, role\* |
| People | authors of indexed papers and halide/Halide committers | Halide contributor\*, anchor author, papers in the index, cites anchor, affiliation\* |
| Anchors | the Halide works themselves | none — sixteen records |

\* Hidden until the data carries the field. `role` and `importance` arrive with curation;
`affiliation` arrives with `data/pools/authorship.json`; the contributor facet and the
commits sort arrive with `data/people/halide_contributors.json`; cleanup status, language, stars and
descriptions arrive with `data/pools/lane_b_curatable.json`, which the build merges onto
`lane_b_classified.json` where it has an opinion — the classified pool stays the base
because it is the only file covering bundles and prose-only repositories. Nothing needs a front-end change
when they land: the facet appears because a record has the field.

## Edges

The index is a graph, so every card carries the edges leading out of it and following one
navigates to the node at the far end.

- paper → the repositories it published as artifacts, and the repositories it merely names
- repository → the papers it is the artifact of
- person → the papers they wrote, any anchor work they authored, and the repositories they
  committed to with their commit count and share of the tree
- author names on a paper card → that person's node
- anchor → its citing works, as a filter rather than a stored reverse edge

A repository that is not itself in the index — a vendored bundle before the bundles are
loaded — renders as a plain outbound GitHub link rather than an in-page edge.

## Three classes of record are gated rather than faceted

They answer "should this be in the corpus at all", which is a different question from
"which of these do I want", and mixing them into the facets would make the facet counts
disagree with the header.

- **Vendored bundles**, 2,828 repositories whose only Halide arrived inside a third-party
  dependency. Off by default and shipped in `data/site/halide-bundles.json`, fetched only
  when the button is pressed.
- **Retired duplicates**, the 93 records the duplicate classification retired in favour of
  another. Off by default; each card names the survivor and why.
- **Dropped repositories**, the ones the cleanup pass judged redistributed copies or
  unmodified re-uploads. Kept with their reason rather than deleted, off by default.
- **DOI-only records**, the 161 works Semantic Scholar's 1,000-result cap hid. Shown by
  default, since the citation is real. Where `data/pools/doi_enriched_state.json` has a
  record they carry a real title, venue, year, authors and citation count and keep the tier
  only as provenance; without it they render as bare identifiers.

## Two rules the page keeps

- **No silent truncation.** Every capped list says so: a facet header reads `(183)`,
  `(top 200 of 553)`, or `(7 of 553)` when its own search box is filtering, and the results
  list says how many of how many it is showing next to the button that shows the rest.
- **A facet with no values does not render.** An empty box invites the reader to conclude
  the data is empty rather than absent.
