# Blind both Reviewers in Dual mode; let Conflict resolution land on a fresh decision

Slice 5 needed a way for a Dual Review Project's Owner and Co-Reviewer to screen the same Citations independently, per PRISMA's dual-review guidance. We decided both Reviewers see neither the AI Suggestion nor the other's Screening Decision until they've recorded their own — including whichever of the two opens a Citation *first*, who has no peer decision yet but would otherwise get v1's "see AI Suggestion, then decide" flow. Letting the first opener see it while the second doesn't would make one of the two "independent" decisions AI-anchored and the other not, undermining the reason blinding exists at all. Solo Review Projects are unaffected — the AI Suggestion still shows upfront there, exactly as in v1.

Separately, when the two recorded decisions differ and a Conflict is held, the Owner isn't limited to picking one of the two original values (the pattern Possible Duplicate uses for merge conflicts) — they can enter a different decision entirely. Real conflict resolution is usually a discussion between the two Reviewers that lands somewhere neither's initial read did; constraining the Owner to the original two values would misrepresent how that resolution actually happens.

## Considered Options

- **Show AI Suggestion upfront to both, blind only the peer's decision**: simpler, reuses v1's existing flow untouched — rejected because it still lets the AI anchor both reviewers' "independent" judgment, which defeats the point of dual review.
- **Constrain Conflict resolution to picking one of the two recorded decisions** (mirroring Possible Duplicate exactly): more consistent with existing precedent, but rejected because it would silently misrepresent a resolution that was actually a fresh agreement, not a pick between the original two.

## Consequences

- Solo and Dual projects now have genuinely different screening interaction flows: Solo shows the AI Suggestion immediately, Dual withholds it from both Reviewers until each has independently decided. Deliberate, not an inconsistency to "fix" later.
- Citation responses must be shaped per viewing Reviewer (has this Reviewer decided yet?), not just per Citation — a new kind of gating v1 and Slice 2/3 never needed.
- A resolved Conflict's final decision may match neither Reviewer's original one; CSV export (per Q15 of the Slice 4+5 design conversation) must show both original decisions alongside the final one so this is never silently lost.
