# Extraction field definitions are not locked, unlike Criteria

Criteria locks after the first Screening Decision, so changing the rules can't silently invalidate decisions already made against them. For Slice 2's Reviewer-defined extraction fields, we decided against the same lock-on-first-use rule: extraction is more iterative than screening — a Reviewer often discovers a field worth capturing partway through a review — so we kept the field list editable throughout instead of matching the Criteria pattern.

## Consequences

Deleting a field that already has recorded values soft-deletes it (archived, hidden from the active list, existing values retained) rather than hard-deleting, so an in-progress edit can't destroy already-extracted data — the same risk Criteria's lock prevents outright, mitigated here a different way.
