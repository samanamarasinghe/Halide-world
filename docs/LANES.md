# Lane claims

Two sessions work this repo in parallel and both push to `main`. On 2026-08-19 they
independently built the same author dedupe within minutes of each other and pushed to the
same two paths; the second push won and the first session's work was thrown away. Nothing
was corrupted — the blob-SHA check and the memory version tokens both did their job — but
the wasted effort was real, and splitting the work by *subject* did not prevent it.

Splitting by subject fails because two sessions reason about the same problem and reach for
the same filename. Splitting by **path** does not, because a path collision is visible
before any work starts.

## The protocol

1. **Before starting a lane**, run `git fetch && git log --oneline origin/main -10`. A
   commit touching your intended paths means the lane is taken.
2. **Claim the paths here** in the same commit as your first real change, so the claim and
   the work arrive together and a claim never sits stale over an abandoned lane.
3. **Do not write a path another lane claims.** Raise it instead — the other session has
   context you do not.
4. **A push rejected for a stale SHA is a collision, not a retry.** Re-read the file and
   look at what landed before pushing again; the other session may have solved your problem
   already.

Step 1 is the one that actually gets skipped. The affiliations lane was started without it
on 2026-08-19 and only checked at push time; it happened to be free, which was luck rather
than process.

## Claims

| paths | lane | claimed |
|---|---|---|
| `harvest/*`, `data/pools/lane_*` | harvest | 2026-08-18 |
| `curate/cleanup_repos.py`, `curate/fork_diff.py`, `curate/enrich_*.py`, `data/pools/fork_verdicts.json` | repo cleanup and enrichment | 2026-08-18 |
| `curate/tier_split.py`, `curate/rules_pass.py`, `curate/extract_pdf_text.py`, `data/pilot/TIER_SPLIT.md`, `data/pilot/RULES_PASS.md` | curation: tiers, rules, the judged pass | 2026-08-19 |
| `curate/author_dedupe.py`, `data/pilot/AUTHOR_DEDUPE.md`, `data/pools/author_dedupe.json` | person layer: author-side dedupe | 2026-08-19 |
| `curate/person_aliases.py`, `data/pools/person_aliases.json`, `docs/name_matching.md` | person layer: cross-layer contributor/author aliases, and name-matching method | 2026-08-19 |
| `curate/repo_contributors.py`, `curate/contributor_harvest.py`, `curate/contributor_edges.py`, `curate/contributors.py`, `data/people/halide_contributors.json`, `data/pilot/CONTRIBUTOR_PILOT.md`, `data/pilot/CONTRIBUTOR_HARVEST.md`, `data/pilot/CONTRIBUTOR_EDGES.md`, `data/pools/contributor_harvest.json`, `data/pools/contributor_edges.json` | contributor lane | 2026-08-18 |
| `build_site.py`, `index.html`, `assets/*`, `data/site/*`, `patch_*.py` | site and GUI | 2026-08-18 |
| `curate/artifact_edges.py`, `curate/admit_artifact_repos.py`, `data/pilot/ARTIFACT_EDGES.md`, `data/pools/artifact_edges.json`, `data/pools/artifact_repos.json` | artifact edges: paper -> repo, and admitting the repos Lane B cannot see | 2026-08-19 |
| `curate/fulltext_evidence.py`, `data/pools/fulltext_evidence.json` | full-text evidence: telling a Halide sentence from a reference line | 2026-08-19 |
| `curate/resolve_dois.py`, `curate/harvest_affiliations.py`, `curate/affiliations.py`, `data/pools/s2_doi_map.json`, `data/pools/affiliations_state.json`, `data/pilot/AFFILIATIONS.md` | affiliations: where they were when that happened | 2026-08-19 |

The person layer is deliberately two rows, not one. The two halves must *run* together —
a contributor joined "to the author record" joins one of several until the author side is
deduped — but they are separate files and can be built independently.

## The data lane wrote across the site lane's claim, twice, on his instruction

`build_site.py` belongs to the site lane. It has been edited from the data lane twice, both
times because he said to: once to render the artifact-edge repos, and on 2026-08-19 via
`patch_person_edges.py` to point the person layer at `contributor_edges.json` and
`affiliation_edges.json`. Both are flagged rather than silent.

What that patch changed, so the site lane is not surprised by it:

- The page read `data/people/halide_contributors.json`, which covers halide/Halide alone —
  **222 people with contribution data out of 886**, and no edge carrying a category, so the
  24 people who EXTENDED Halide outside the anchor were invisible. It now reads
  `contributor_edges.json`: **884 people with contributions, 232 in more than one repo.**
- Affiliations were read from `data/pools/authorship.json`, **a filename nothing ever
  produced**. The real output is `affiliation_edges.json`, which is why every build has
  reported `people_with_affiliation: 0`. Person nodes now carry `affiliations`,
  `affiliation_spans` (institution + first/last year + n_papers) and `n_institutions`.
- **`contrib_commits` deliberately still means commits to halide/Halide**, because the
  People score and its default sort are calibrated on it. Cross-repo totals arrive beside
  it as `contrib_commits_total` rather than silently reordering the People view. New
  fields: `contrib_repos`, `contrib_categories`, and `category` on each contribution.
- **A placeholder guard was added to the site-side join.** The join is exact display name,
  and with 886 contributors instead of 227 that merged **ten unrelated people onto one
  `git:unknown` node and two onto `git:root`** — the same failure `contributors.py` denies
  at the git layer, reappearing one layer up. Unmatched contributors are now keyed on the
  contributor lane's unique `person_id`, not on their display name.
- Second bug from the same pass: two contributor records can land on ONE author node (S2
  abbreviates given names, so `Sander Vocke` joins `S. Vocke` through the reviewed
  `author_id` while the display names never match). `contrib_repos` was assigned rather
  than accumulated and reported one repo for a person carrying nine.

New `build-info.json` counts: `people_who_extend`, `people_in_many_repos`,
`people_at_many_institutions`. The patch round-trips: applied to the pushed
`build_site.py` it reproduces the tested file byte for byte.

## Cross-lane dependency, contributor lane to person layer

`contributor_edges.py` imports `contributors.py`'s merge rules **unchanged** and runs them
over both populations at once — the anchor's 227 people and the harvest's 893 emails are
one population observed twice, and 87 core contributors turn out to appear outside the
anchor. Anyone changing the anchor's rules changes the whole git-side person layer with it.

The cross-layer join to *authors* still comes only from the hand-reviewed
`person_aliases.json`, per his ruling that the initial-only key is never automated. That
leaves **16 of 886 git people carrying an `author_id`**, which is the largest unjoined
surface in the index and the next place review effort pays.

## A derived input the contributor lane rebuilds rather than commits

`data/pools/lane_b_curatable.json` is `cleanup_repos.py`'s output and the contributor
runner's input, and it existed only on one disk because it is built from the gitignored
`repo_meta_state.json`. `contributor_harvest.py` now rebuilds both when they are missing
instead of failing, so the lane starts from a bare clone. It also falls under the harvest
lane's `data/pools/lane_*` claim, which is the second reason not to commit it from here.

`data/people/halide_contributors.json` is the same shape of problem — it needs a clone of
halide/Halide — and `contributor_edges.py` bootstraps it the same way (blobless bare,
~27MB).

## Not covered by claims

`data/anchors.json`, `data/pools/duplicates.json` and anything else carrying judgement
rather than derived output. Those are edited rarely and by agreement, never as a side
effect of a lane.

## Cross-lane dependency, affiliations to person layer

`docs/name_matching.md` (cross-layer alias lane) concludes that affiliation strings are the
remedy for the altered-name blind spot, and `data/pilot/AUTHOR_DEDUPE.md` names them as the
next signal for its unresolved groups. Both are *consumers* of this lane's output, not
owners of it. That dependency has now been discharged once: affiliations were folded into
`author_dedupe.py` and took its residual from 143 groups to 117. When affiliation coverage
improves, re-run the dedupe rather than editing either consumer by hand.

## Note for the curation lane on full-text evidence

`curate/extract_pdf_text.py` and its output `data/pools/fulltext_state.json` belong to the
curation lane and were not edited from here. But a finding that changes how they should be
read is recorded in `curate/fulltext_evidence.py`, in this lane: **a "Halide sentence" is
often a line from the paper's own bibliography.**

Of the 1,062 papers, **197 have no Halide sentence outside their reference list and 61 have
no Halide sentence at all, so the citation-only population is 258** — not the 61 a raw hit
count reports. The judged pass should read the `body` / `bibliography` / `none` verdict
rather than the hit count.

Four signals decide it, each added because the previous set got a real case wrong: venue
tails, a verbatim anchor title covering >=30% of the sentence, a leading `[16]` citation
marker, and an author-list run. `arXiv:` was tested and rejected — it appears in the
page-margin stamp of every preprint and sits inside body sentences.

## Note for the curation lane

He ruled on 2026-08-19 that the repos reachable only through an artifact edge do enter the
repo pool. `curate/admit_artifact_repos.py` prepares them: **198 candidates, 10 rejected at
the head by hand review, 188 admitted**, 11 flagged `unverified_name`.

**They arrive with no `signatures`, `paths` or `n_matches`, because code search never found
them.** Any rule, tier score or facet keyed on those fields reads zero and will conclude
"no Halide evidence" — dropping exactly the repos this lane exists to surface. Every record
carries `discovered_via: artifact_edge`; branch on it, and read the parent paper instead.
That is +188 records for the judged pass on top of the 262 already queued.
