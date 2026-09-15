# Auto-merge duplicate Citations by default, escalating only on Reviewer-data conflicts

Slice 3 needed a way to collapse Duplicate Citations uploaded across batches/sources without forcing a confirm-click on every match — the pattern every other AI-touching feature in this app follows (AI Suggestion, Full-Text Suggestion) would reintroduce exactly the tedium this slice exists to remove. We decided Duplicates matched by DOI or normalized title merge silently by default — the losing Citation is archived (not deleted) with a pointer to the survivor, mirroring how Extraction Field handles archiving — *except* when the two Citations already carry conflicting Reviewer-entered data (a Screening Decision, Full-Text Decision, Extraction Value, or Full Text), in which case the merge is held as a Possible Duplicate for manual resolution instead.

Reviewer-entered data never gets silently dropped by a merge, one-sided or not: when the survivor lacks a value the loser has, it's copied onto a new row keyed to the survivor, never moved by reassigning the loser's existing row to point at the survivor. The loser's own copy stays exactly where it was, so archiving still means what it means for Extraction Field — the data survives, findable via the provenance pointer, not silently absorbed. Full Text specifically transfers through the existing attach/replace code path rather than a raw copy, so Full-Text Suggestion's regenerate-on-replace rule applies without new logic.

How much bibliographic data (abstract, authors, year, source) actually folds into the survivor is itself a Review Project-level choice — Merge Mode, decided once at creation alongside Criteria. **Combine** gap-fills missing fields and merges `source` into the full list of databases a paper was found in; **Keep First** leaves the survivor's bibliographic fields exactly as first uploaded. This choice never touches Reviewer-entered data: that always transfers one-sided and still escalates to a Possible Duplicate on genuine conflict, under either mode — losing a recorded decision because a Reviewer picked the more conservative mode would undermine the whole reason the escalation valve exists.

## Considered Options

- **Always require manual confirmation**: matches the safety precedent set elsewhere in the app, but rejected in favor of speed — low-friction auto-merge was the explicit goal.
- **Always merge deterministically, even on conflict**: simpler, but silently discards a Reviewer's own recorded judgment, which no other feature in this codebase does.
- **One global merge behavior, no per-project choice**: simpler still, but some Reviewers' source exports are clean enough that aggressive bibliographic merging is safe, while others would rather see duplicates flagged with minimal data-mixing. Rejected in favor of a one-time choice at project setup.

## Consequences

- Matching is exact-only (DOI, or normalized title) — no fuzzy/similarity matching in this slice, so near-duplicates with differing titles and no DOI won't be caught.
- A Citation is only matched against its own current fields, not every identifier ever absorbed into it. A three-way duplicate that matches pairwise on different keys (A~B by DOI, B~C by title only, A and C don't directly match) can leave one Citation unmerged. Documented gap, not solved here.
- `Citation.source` moves from a single string to an array (matching `authors`), since a merged Citation now records every source it was found in, not just one.
