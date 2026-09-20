import csv
import io
import re

from asr_backend import models, screening

CSV_HEADER = [
    "title",
    "abstract",
    "authors",
    "year",
    "source",
    "screening_decision",
    "reason",
    "ai_suggestion_decision",
    "ai_suggestion_reason",
    "full_text_decision",
    "full_text_reason",
]

# Dual-only columns (#30): `screening_decision` above already carries the
# final/resolved decision (Owner's own call, or a Conflict's resolution once
# one lands), so these two add the Owner's and Co-Reviewer's individual
# decisions alongside it for a PRISMA-style inter-rater audit trail. Appended
# only for a Dual Review Project's export, so a Solo export stays unchanged.
DUAL_REVIEWER_HEADER = [
    "owner_decision",
    "co_reviewer_decision",
]

_SLUG_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def slugify(value: str) -> str:
    slug = _SLUG_NON_ALNUM.sub("-", value.lower()).strip("-")
    return slug or "review-project"


def build_export_filename(review_project: models.ReviewProject) -> str:
    id_suffix = str(review_project.id).split("-")[0]
    return f"{slugify(review_project.name)}-{id_suffix}.csv"


def build_export_csv(
    review_project: models.ReviewProject,
    citations: list[models.Citation],
    requester: models.Reviewer,
) -> str:
    """The Review Project's export, as `requester` is allowed to see it.

    In a Dual project, a Citation the requester has not screened yet has its
    peer decisions, final decision and AI Suggestion columns left blank, the
    same per-Citation blinding as the detail view (ADR 0006, #54). Once the
    requester has decided it, that row shows everything. Solo is never blinded.
    """
    buffer = io.StringIO()
    _write_criteria_header(buffer, review_project.criteria)
    is_dual = review_project.review_mode == "dual"
    extraction_fields = review_project.active_extraction_fields
    writer = csv.writer(buffer)
    header = [*CSV_HEADER, *(DUAL_REVIEWER_HEADER if is_dual else [])]
    writer.writerow([*header, *(field.name for field in extraction_fields)])
    for citation in citations:
        blind = screening.is_blind(
            review_project, citation.screening_decision_for(requester.id)
        )
        row = [
            citation.title,
            citation.abstract or "",
            "; ".join(citation.authors),
            citation.year or "",
            "; ".join(citation.source),
            "" if blind else citation.decision_label,
            "" if blind else citation.screening_reason,
            "" if blind else citation.ai_suggestion_decision_label,
            "" if blind else citation.ai_suggestion_reason_label,
            citation.full_text_decision_label,
            citation.full_text_reason_label,
        ]
        if is_dual:
            # Blind means the requester has no decision of their own here, so
            # neither column is theirs: both are the peer's (or a former peer's).
            row += (
                ["", ""]
                if blind
                else [citation.owner_decision_label, citation.co_reviewer_decision_label]
            )
        row += [citation.extraction_value_for(field.id) for field in extraction_fields]
        writer.writerow(row)
    return buffer.getvalue()


def _write_criteria_header(buffer: io.StringIO, criteria: models.Criteria | None) -> None:
    # A Criteria's PICO/exclusion-rules/notes fields don't fit the
    # row-per-Citation CSV shape, so they go in a "# "-prefixed block above the
    # header row instead. This isn't valid CSV on its own — a consumer parsing
    # the Citation rows must skip these leading lines first — but it keeps the
    # export a single downloadable file. Nothing is written when a Review
    # Project has no Criteria saved yet.
    if criteria is None:
        return
    lines = [
        "# Review Project Criteria",
        f"# Population: {criteria.population or ''}",
        f"# Intervention: {criteria.intervention or ''}",
        f"# Comparison: {criteria.comparison or ''}",
        f"# Outcome: {criteria.outcome or ''}",
        f"# Exclusion Rules: {'; '.join(criteria.exclusion_rules)}",
        f"# Notes: {criteria.notes or ''}",
        "",
    ]
    buffer.write("\r\n".join(lines) + "\r\n")
