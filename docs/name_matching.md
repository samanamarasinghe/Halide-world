# Name matching: what was tried, and what does not work

Both halves of the person layer key on names — `curate/author_dedupe.py` groups author ids
by identical name, `data/pools/person_aliases.json` joins git contributors to authors the
same way. The Ankit Aggarwal case showed the key is not safe: the metadata source stored
`Ankita Aggarwal` where the paper's own author list (arXiv 2602.19762) prints `Ankit`. A
name the source altered means a person can split under two *different* names and never
enter a duplicate-name group at all, so neither tool can see them.

This note records the attempt to find those cases from inside the data, and why it failed.
Kept so it is not rebuilt.

## Attempt: near-name pairs, gated by shared coauthors

Over the 5,662 records carrying a source author id, blocked by surname, comparing given
names that are both spelled out (initialized forms are a separate, known effect and were
skipped — 4,179 of them).

| filter | pairs | with shared coauthors |
|---|---|---|
| given-name edit distance ≤ 2 | 2,459 | **44** |
| one given name a strict prefix of the other, ≥4 chars, +1–2 letters (the Ankit→Ankita shape) | 32 | **4** |

**Both are noise.** The shared-coauthor gate does not save it, because the false pairs are
lab colleagues, who of course share collaborators:

- `Fan Yang` vs `Mao Yang` — 28 shared coauthors, both MSRA, two well-known and different people
- `Tianqi Chen` vs `Jinqi Chen` — 8 shared
- `Jing Li` vs `Ling Li`, `Zhi Chen` vs `Wei Chen`, `Jie Zhao` vs `Jieyu Zhao` — same shape

The tightened prefix rule fails the same way. Its best candidate, `Guangli Li` vs
`Guanglin Li` (7 shared coauthors), is **two different people**: Guangli Li (李广力) works
on compilers at ICT/CAS, Guanglin Li (李光林) on biomedical engineering at SIAT/CAS. Same
academy, different institutes, different characters. `Zhen Zhang` vs `Zheng Zhang` is
likewise two people.

## Why it cannot work

Short given names are within edit distance 2 of many other valid given names, so the
pattern that catches a one-character corruption also catches every colleague whose name
differs by one character. Making the gate stricter does not separate them, because the
discriminating fact — which human wrote which paper — is not in the name at all.

## What to do instead

**Do not add name-similarity matching.** The remedy for a corrupted name is a signal that
is not a name:

- **Affiliation strings**, which the affiliations lane produces. Already the planned next
  signal for the 143 groups `author_dedupe.py` leaves split, and the right one here too:
  Guangli/Guanglin Li separate immediately on institute, and would have separated Ankit
  Aggarwal's Qualcomm record without any name reasoning.
- **The paper's own author list**, when a specific case matters. That is what settled
  Ankit Aggarwal, and it is checkable in a way a name-distance score is not.

Meanwhile the blind spot is bounded but real, and stated rather than papered over: a
person whose name the source altered is invisible to the current tools, and we have no
estimate of how many there are — only that name similarity will not find them.
