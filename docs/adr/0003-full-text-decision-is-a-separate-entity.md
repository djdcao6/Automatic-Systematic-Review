# Full-text screening is a separate decision, not an edit to Screening Decision

Slice 2 adds a full-text review stage after title/abstract screening. We considered reusing v1's `ScreeningDecision` — overwriting it once full text is reviewed, keeping "one decision per Citation" — but decided instead to introduce a new `FullTextDecision` entity, independent from `ScreeningDecision`. PRISMA reports title/abstract and full-text exclusions as distinct counts, and Slice 6 (PRISMA flow diagram) needs to know *which stage* excluded a Citation; overwriting the original decision would destroy that provenance.

## Consequences

A Citation can now carry two independent decisions instead of one. A `FullTextDecision` of Include/Exclude also resolves an otherwise-terminal Maybe from the title/abstract stage. Any existing logic that assumed exactly one decision per Citation (status labels, counts, CSV export) needs to account for both.
