# Automatic Systematic Review

Helps researchers run systematic reviews: defining inclusion/exclusion criteria, screening citations against them with AI assistance, and (later) extracting structured data from full texts.

## Language

**Review Project**:
A single systematic review: its Criteria, uploaded Citations, and their Screening Decisions, owned by one Reviewer. A Reviewer may own several Review Projects; Citations can be uploaded into one incrementally, across more than one batch.
_Avoid_: Review, Study, Workspace

**Criteria**:
The inclusion/exclusion rules for a Review Project, applied to every Citation in it: PICO fields (Population, Intervention, Comparison, Outcome — all optional), an explicit list of exclusion rules (e.g., language, publication type, date range, study design), and free-text notes. Locked once the first Screening Decision is recorded — v1 has no mid-review editing.
_Avoid_: Inclusion criteria, Filters

**Citation**:
A single title/abstract record uploaded for screening: title, abstract, authors, publication year, and source. Distinct from the full text of the paper, which is out of scope for this slice. A Citation missing an abstract stays visible but flagged, since it can't receive an AI Suggestion.
_Avoid_: Reference, Record, Paper

**Screening Decision**:
The three-state outcome — Include, Exclude, or Maybe — that a Reviewer records for a Citation against a Review Project's Criteria, with an optional reason. Editable at any time. "Maybe" is a terminal state in v1: there's no follow-up workflow to resolve it further yet.
_Avoid_: Unsure, Undecided, Verdict

**AI Suggestion**:
A proposed Screening Decision plus a reason, generated once on demand when a Reviewer first opens a Citation and persisted from then on — not regenerated on later views. Always advisory, and stored separately from the Reviewer's final Screening Decision — even when they match — so AI accuracy can be reviewed later.
_Avoid_: AI decision, Auto-screening

**Reviewer**:
The single person who owns a Review Project and makes its final Screening Decisions in v1. Future versions may support multiple Reviewers per PRISMA's dual-review guidance.
_Avoid_: User, Screener
