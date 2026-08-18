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
facets that mean something for them; everything else — search, sort, the 200-value cap,
the result cap — is shared.

| View | Nodes | Facets |
|---|---|---|
| Papers | works citing an anchor | cites anchor, year, venue, citation intent, artifact, field, role\* |
| Repositories | repositories with Halide in them | verdict, evidence, signature, where it sits, paper artifact, cleanup status\*, language\*, role\* |
| People | authors of indexed papers and halide/Halide committers | contributions, anchor author, cites anchor, affiliation\* |
| Anchors | the Halide works themselves | none — sixteen records |

\* Hidden until the data carries the field. `role` and `importance` arrive with curation;
`affiliation` arrives with `data/pools/authorship.json`; the contributor half of the
Contributions facet and the commits sort arrive with `data/people/halide_contributors.json`;
cleanup status, language, stars and descriptions arrive with
`data/pools/lane_b_curatable.json`, which the build merges onto `lane_b_classified.json`
where it has an opinion — the classified pool stays the base because it is the only file
covering bundles and prose-only repositories. Nothing needs a front-end change when they
land: the facet appears because a record has the field.

## Edges

The index is a graph, so every card carries the edges leading out of it and following one
navigates to the node at the far end. The `Show connectivity` button opens them all at
once; each card also has its own toggle.

- paper → the repositories it published as artifacts, and the repositories it merely names
- repository → the papers it is the artifact of
- person → the papers they wrote, any anchor work they authored, and the repositories they
  committed to with their commit count and share of the tree
- author names on a paper card → that person's node
- anchor → its citing works, as a filter rather than a stored reverse edge

## Two person facets worth explaining

**Contributions** merges what someone authored with what they committed: the paper bands
plus `Committed to halide/Halide`, which sorts first because committing is a different kind
of contribution rather than the smallest one. Every value starts selected, so unlighting one
removes that group. Anchor works count towards a person's band — without that, an author
whose only indexed work is an anchor carries no value at all and vanishes from a facet whose
values are all lit.

**Total contributions** is the default sort: commits divided by the largest commit count in
the index, plus papers divided by the largest paper count. Both denominators are measured at
load rather than fixed, because both move as the index grows. The figure is internal: it
orders the list and is not printed on the cards. It is a display ordering, not a judgement
of importance — that is what curation will assign.

A contributor is joined to an author node only on an exact display-name or alias match, and
anyone unmatched appears as their own entry. A wrong merge in a person index silently
reassigns authorship, which is worse than showing one person as two rows. Note that Semantic
Scholar abbreviates given names, so `A. Adams` and `Andrew Adams` will not join under this
rule.

## What the page leaves out

Two classes of record never reach it, both excluded by the build rather than hidden behind a
control, and both still counted in the build report so the arithmetic stays checkable.

- **Retired duplicates**, the 93 records the duplicate classification retired in favour of
  another. Their survivor carries the work, and a page offering both would offer the same
  paper twice.
- **Dropped repositories**, the 102 the cleanup pass judged to carry only someone else's
  Halide-touching source — a redistributed copy, or an unmodified re-upload of Halide. They
  are kept in `data/pools/lane_b_curatable.json` with the reason recorded, which is where a
  wrong drop is audited; `lane_b_curatable_summary.json` lists every one.

The 2,828 vendored bundles — repositories whose only Halide arrived inside a third-party
dependency — are NOT among them. They carry `third_party_bundle` as their verdict and are
filtered through the Verdict facet like any other repository.

**DOI-only records**, the 161 works Semantic Scholar's 1,000-result cap hid, are shown by
default: the citation is real. Where `data/pools/doi_enriched_state.json` has a record they
carry a real title, venue, year, authors and citation count and keep the tier only as
provenance; without it they render as bare identifiers.

## What each view opens on

| View | Default sort | Why |
|---|---|---|
| Papers | Citation contexts | How much the citing work engages with an anchor, rather than its standing elsewhere |
| Repositories | Signature matches | Volume of Halide references in the tree — see the caveat below |
| People | Total contributions | Commits and papers on one axis |
| Anchors | Citations in this index | Which anchor the literature actually builds on |

`Clear filters` restores the sort as well as the facets, so a view's default is always
reachable.

**Signature matches is not an impact measure.** For a repository carrying a vendored Halide
tree the count includes Halide's own files, so it says how much Halide-shaped code sits in
the tree and not how much the project does with it. Sorting by stars is the quicker route to
the projects people actually use.

## Two rules the page keeps

- **No silent truncation.** Every capped list says so: a facet header reads `(183)`,
  `(top 200 of 553)`, or `(7 of 553)` when its own search box is filtering, and the results
  list says how many of how many it is showing next to the button that shows the rest.
- **A facet with no values does not render.** An empty box invites the reader to conclude
  the data is empty rather than absent.
