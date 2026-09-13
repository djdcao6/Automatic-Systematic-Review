# Solo reviewer for v1, deferring PRISMA dual-independent review

PRISMA guidance recommends two independent reviewers screen each citation, with a defined process to resolve disagreements. We decided v1 supports exactly one Reviewer per Review Project, with no second reviewer or conflict-resolution step, to ship the core AI-assisted screening loop first.

## Consequences

Output from v1 isn't sufficient on its own for a fully PRISMA-compliant published review — a second independent pass would need to happen outside the tool. Adding dual-review later means changing Screening Decision from a single value per Citation to one value per Reviewer plus a resolution step, not just adding a second user.
