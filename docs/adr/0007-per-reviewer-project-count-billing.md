# Per-Reviewer billing metered by owned-Review-Project count

Slice 8 needed to decide what a Reviewer's Subscription actually pays for, and who it attaches to. We decided billing attaches directly to the Reviewer account — no Team/Workspace entity above it — and the Free Plan's limit is metered by how many Review Projects a Reviewer owns (capped at 1; Paid removes the cap), rather than by AI usage or by gating a specific feature.

## Considered Options

- **AI-usage metering** (cap AI Suggestion / Full-Text Suggestion / Search Terms calls per month): ties the paywall to Slice 8's actual cost driver (Anthropic API spend), but needs usage-counting and monthly-reset infrastructure this app has nowhere else, for a threshold that's harder to communicate to a Reviewer than "1 free Review Project."
- **Feature-gating** (e.g. Dual Review Mode, or Slice 2's full-text features, behind Paid): rejected — whether a Reviewer collaborates or reads full texts is a research-methodology choice, not something that should be entangled with ability to pay.
- **Team/Workspace-scoped billing** (a Subscription attaches to a group that Reviewers join): rejected — no such entity exists anywhere else in this domain (a Review Project already has exactly one Owner), and inventing one purely for billing would be speculative scope this slice doesn't need.

## Consequences

- Adding Team-scoped billing later isn't a config change — it needs a new entity above Reviewer and a migration for every existing Subscription/Review Project relationship.
- The paywall's pressure point is "how many Review Projects have you started," not "how much AI have you used" — an Owner running heavy AI usage on one Review Project pays the same as one barely touching it. If Anthropic cost ever becomes the real constraint, that's a second, independent metering axis to add later, not a reason to revisit this one.
- Co-Reviewer participation is free regardless of the Co-Reviewer's own Plan — only the Owner's Plan is ever checked, per `CONTEXT.md`'s Plan definition.
