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
The three-state outcome — Include, Exclude, or Maybe — that a Reviewer records for a Citation against a Review Project's Criteria at the title/abstract stage, with an optional reason. Editable at any time. A Maybe stands indefinitely unless a Full-Text Decision is later recorded for that Citation, which resolves it. In a Dual Review Project, the Owner and Co-Reviewer each record their own independently; a Conflict is held when they disagree.
_Avoid_: Unsure, Undecided, Verdict

**AI Suggestion**:
A proposed Screening Decision plus a reason, generated once on demand when a Reviewer first opens a Citation and persisted from then on — not regenerated on later views. Always advisory, and stored separately from the Reviewer's final Screening Decision — even when they match — so AI accuracy can be reviewed later. Never pre-selects the Screening Decision or fills in its reason, and is generated after the Citation is shown, so the Reviewer never waits on it. In a Dual Review Project, withheld from both the Owner and Co-Reviewer until each has independently recorded their own Screening Decision, so neither's judgment is AI-anchored.
_Avoid_: AI decision, Auto-screening

**Conflict**:
Held when a Dual Review Project's Owner and Co-Reviewer record different Screening Decisions for the same Citation. Sits in a dedicated queue until the Owner resolves it — either by picking one of the two recorded decisions or entering a different decision reached through discussion — which becomes the Citation's final Screening Decision. Both original decisions remain on record afterward.
_Avoid_: Disagreement, Discrepancy

**Invitation**:
A shareable link/token an Owner generates to add a Co-Reviewer to a Dual Review Project. Valid until accepted or revoked by the Owner (no automatic expiry); accepting it registers a new Reviewer account on the spot if the recipient doesn't already have one, or attaches an existing one.
_Avoid_: Invite code, Access token

**Full Text**:
The PDF of a Citation's full paper, attached by a Reviewer independently of its Screening Decision — Include and Maybe Citations are the primary candidates, but any Citation can have one attached. Parsed to text to support the Full-Text Decision and Extraction Fields; a PDF that can't be parsed (e.g. a scan with no text layer) is flagged for manual entry instead.
_Avoid_: PDF, Document, Paper

**Full-Text Decision**:
The three-state outcome — Include, Exclude, or Maybe — that a Reviewer records for a Citation after reading its Full Text, with a reason drawn from the Review Project's Criteria exclusion rules. Recorded separately from, and independently of, the Citation's Screening Decision; resolves an outstanding Maybe from that earlier stage.
_Avoid_: Full-text screening result, Second decision

**Full-Text Suggestion**:
An AI-proposed Full-Text Decision plus reason, and AI-proposed values for a Review Project's Extraction Fields, generated once a Citation's Full Text is attached. It is asked for after the Citation page has loaded, never while it loads, and it fills nothing a Reviewer owns: the Full-Text Decision starts with no choice, and each Extraction Value starts empty with the AI's value beside it for the Reviewer to use. Unlike an AI Suggestion, regenerates if the Full Text is replaced — a new PDF is new source content, not just a repeat view — and a suggestion still being written for the old PDF is discarded.
_Avoid_: AI extraction, Auto-extraction

**Extraction Field**:
A free-text data point a Reviewer defines per Review Project to capture from a Citation's Full Text (e.g. sample size, methodology). Unlike Criteria, not locked once in use — a Reviewer can keep editing the field list through a review. Deleting a field that already has recorded values archives it rather than discarding the data.
_Avoid_: Data point, Schema field

**Subscription**:
The Stripe-backed record of a Reviewer's paid billing relationship. Exists only once a Reviewer has started checkout; its status (active, canceled, past due, etc.) is kept in sync via Stripe webhooks and determines whether that Reviewer is on the Paid Plan. A Reviewer with no Subscription, or one that's canceled/expired, is on the Free Plan.
_Avoid_: Billing record, Payment

**Plan**:
A Reviewer's current capability level — Free or Paid — derived live from their Subscription's status, never stored independently of it. Paid removes the Free Plan's cap on how many Review Projects a Reviewer may own. A Reviewer's Plan only ever affects Review Projects they own; participating as a Co-Reviewer on someone else's Review Project is unaffected by either Reviewer's own Plan.
_Avoid_: Tier, Subscription level

**Reviewer**:
An authenticated account (email + password) that can create Review Projects and record Screening Decisions. A Review Project has one Reviewer (Solo Review Mode) or two — its Owner and a Co-Reviewer (Dual Review Mode).
_Avoid_: User, Screener, Account

**Review Mode**:
A Review Project-level choice, made once at creation and never revisited, for how many Reviewers independently screen its Citations. **Solo** has one Reviewer, its Owner, whose Screening Decision is final. **Dual** has an Owner and a Co-Reviewer, each recording an independent Screening Decision per Citation without seeing the other's decision beforehand; a Conflict is held for the Owner to resolve when the two disagree.
_Avoid_: Review type, Screening mode

**Owner**:
The Reviewer who created a Review Project. In a Dual Review Project, the Owner alone invites or removes the Co-Reviewer, edits the Criteria, and has final say resolving a Conflict.
_Avoid_: Admin, Creator

**Co-Reviewer**:
The second Reviewer in a Dual Review Project, invited by its Owner. Records an independent Screening Decision per Citation alongside the Owner's. Reads the Criteria but cannot edit them.
_Avoid_: Second reviewer, Collaborator

**PRISMA Flow Diagram**:
A per-Review-Project report of the screening funnel — records identified (per source, counted before deduplication), duplicates removed, screened, excluded, full-text assessed, excluded with itemized reasons, and included — computed live from current data and viewable at any point in a review, with a plain numeric summary alongside the visual. Adapted rather than a literal reproduction of the official PRISMA 2020 template: omits stages this tool has no data for (records marked ineligible by automation, reports sought but not retrieved) and the qualitative/quantitative synthesis split.
_Avoid_: Report, Chart, PRISMA diagram

**Search Terms**:
A Reviewer-editable set of AI-suggested search terms for a Review Project, generated on demand from its Criteria's PICO fields: terms grouped by PICO concept (Population, Intervention, Comparison, Outcome), plus a combined boolean query string always derived from those groups (terms within a concept OR'd, concepts AND'd together). Purely advisory — the Reviewer copies it into their own database search and uploads results through the existing Citation upload flow; nothing here executes a search or imports Citations automatically. Regenerable at any time, overwriting the prior result in place, independent of whether the Review Project's Criteria has locked. Requires at least one PICO field filled in to generate.
_Avoid_: Query, Search String, Boolean Query, Database Query
