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
A single title/abstract record uploaded for screening: title, abstract, authors, publication year, and source(s). May later have a Full Text attached. A Citation missing an abstract stays visible but flagged, since it can't receive an AI Suggestion. A Citation that loses a Duplicate match is archived rather than deleted, pointing to the surviving Citation, so its data isn't lost.
_Avoid_: Reference, Record, Paper

**Duplicate**:
Two or more Citations in a Review Project identified as the same underlying paper — matched by DOI when both have one, or by normalized title otherwise — and collapsed into one surviving Citation, archiving the rest. Detected automatically whenever Citations are uploaded, including two rows within the same batch, and across batches from different sources. How much of the archived Citation's bibliographic data folds into the survivor is governed by the Review Project's Merge Mode; Reviewer-entered data always transfers when only one side has it, regardless of mode.
_Avoid_: Dupe, Duplicate record

**Possible Duplicate**:
A Duplicate match that can't merge automatically because the two Citations already carry conflicting Reviewer-entered data (Screening Decision, Full-Text Decision, Extraction Values, or Full Text). Held in a dedicated queue until a Reviewer resolves which side's conflicting value is correct. Dismissing a Possible Duplicate as not actually the same paper is permanent, exempting that pair from future automatic matching. Applies the same way regardless of the Review Project's Merge Mode.
_Avoid_: Duplicate candidate, Conflict

**Merge Mode**:
A Review Project-level choice, made once at creation and never revisited, for how a Duplicate's bibliographic fields (abstract, authors, year, source) combine into the surviving Citation. **Combine** gap-fills missing fields and merges `source` into the full list of databases the paper was found in. **Keep First** leaves the survivor's bibliographic fields exactly as first uploaded. Neither mode affects Reviewer-entered data, which always transfers one-sided and still escalates to a Possible Duplicate on a genuine conflict.
_Avoid_: Dedup mode, Merge strategy

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
