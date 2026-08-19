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
| `curate/repo_contributors.py`, `data/pilot/CONTRIBUTOR_PILOT.md` | contributor lane | 2026-08-18 |
| `build_site.py`, `index.html`, `assets/*`, `data/site/*`, `patch_*.py` | site and GUI | 2026-08-18 |
| `curate/artifact_edges.py`, `curate/admit_artifact_repos.py`, `data/pilot/ARTIFACT_EDGES.md`, `data/pools/artifact_edges.json`, `data/pools/artifact_repos.json` | artifact edges: paper -> repo, and admitting the repos Lane B cannot see | 2026-08-19 |
| `curate/fulltext_evidence.py`, `data/pools/fulltext_evidence.json` | full-text evidence: telling a Halide sentence from a reference line | 2026-08-19 |
| `curate/resolve_dois.py`, `curate/harvest_affiliations.py`, `curate/affiliations.py`, `data/pools/s2_doi_map.json`, `data/pools/affiliations_state.json`, `data/pilot/AFFILIATIONS.md` | affiliations: where they were when that happened | 2026-08-19 |

The person layer is deliberately two rows, not one. The two halves must *run* together —
a contributor joined "to the author record" joins one of several until the author side is
deduped — but they are separate files and can be built independently.

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
