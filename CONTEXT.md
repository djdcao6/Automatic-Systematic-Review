# Automatic Systematic Review

Helps researchers run systematic reviews: defining inclusion/exclusion criteria, screening citations against them with AI assistance, then reviewing full texts and extracting structured data from them.

## Language

**Review Project**:
A single systematic review: its Criteria, uploaded Citations, and their Screening Decisions, owned by one Reviewer. A Reviewer may own several Review Projects; Citations can be uploaded into one incrementally, across more than one batch.
_Avoid_: Review, Study, Workspace

**Criteria**:
The inclusion/exclusion rules for a Review Project, applied to every Citation in it: PICO fields (Population, Intervention, Comparison, Outcome — all optional), an explicit list of exclusion rules (e.g., language, publication type, date range, study design), and free-text notes. Locked once the first Screening Decision is recorded — v1 has no mid-review editing.
_Avoid_: Inclusion criteria, Filters

**Citation**:
A single title/abstract record uploaded for screening: title, abstract, authors, publication year, and source. May later have a Full Text attached. A Citation missing an abstract stays visible but flagged, since it can't receive an AI Suggestion.
_Avoid_: Reference, Record, Paper

**Screening Decision**:
The three-state outcome — Include, Exclude, or Maybe — that a Reviewer records for a Citation against a Review Project's Criteria at the title/abstract stage, with an optional reason. Editable at any time. A Maybe stands indefinitely unless a Full-Text Decision is later recorded for that Citation, which resolves it.
_Avoid_: Unsure, Undecided, Verdict

**AI Suggestion**:
A proposed Screening Decision plus a reason, generated once on demand when a Reviewer first opens a Citation and persisted from then on — not regenerated on later views. Always advisory, and stored separately from the Reviewer's final Screening Decision — even when they match — so AI accuracy can be reviewed later.
_Avoid_: AI decision, Auto-screening

**Full Text**:
The PDF of a Citation's full paper, attached by a Reviewer independently of its Screening Decision — Include and Maybe Citations are the primary candidates, but any Citation can have one attached. Parsed to text to support the Full-Text Decision and Extraction Fields; a PDF that can't be parsed (e.g. a scan with no text layer) is flagged for manual entry instead.
_Avoid_: PDF, Document, Paper

**Full-Text Decision**:
The three-state outcome — Include, Exclude, or Maybe — that a Reviewer records for a Citation after reading its Full Text, with a reason drawn from the Review Project's Criteria exclusion rules. Recorded separately from, and independently of, the Citation's Screening Decision; resolves an outstanding Maybe from that earlier stage.
_Avoid_: Full-text screening result, Second decision

**Full-Text Suggestion**:
An AI-proposed Full-Text Decision plus reason, and AI-proposed values for a Review Project's Extraction Fields, generated once a Citation's Full Text is attached. Unlike an AI Suggestion, regenerates if the Full Text is replaced — a new PDF is new source content, not just a repeat view.
_Avoid_: AI extraction, Auto-extraction

**Extraction Field**:
A free-text data point a Reviewer defines per Review Project to capture from a Citation's Full Text (e.g. sample size, methodology). Unlike Criteria, not locked once in use — a Reviewer can keep editing the field list through a review. Deleting a field that already has recorded values archives it rather than discarding the data.
_Avoid_: Data point, Schema field

**Reviewer**:
The single person who owns a Review Project and makes its final Screening Decisions in v1. Future versions may support multiple Reviewers per PRISMA's dual-review guidance.
_Avoid_: User, Screener
