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

The person layer is deliberately two rows, not one. The two halves must *run* together —
a contributor joined "to the author record" joins one of several until the author side is
deduped — but they are separate files and can be built independently.

## Not covered by claims

`data/anchors.json`, `data/pools/duplicates.json` and anything else carrying judgement
rather than derived output. Those are edited rarely and by agreement, never as a side
effect of a lane.
