import csv
import io
import re

from asr_backend import models

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

_SLUG_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def slugify(value: str) -> str:
    slug = _SLUG_NON_ALNUM.sub("-", value.lower()).strip("-")
    return slug or "review-project"


def build_export_filename(review_project: models.ReviewProject) -> str:
    id_suffix = str(review_project.id).split("-")[0]
    return f"{slugify(review_project.name)}-{id_suffix}.csv"


def build_export_csv(
    review_project: models.ReviewProject, citations: list[models.Citation]
) -> str:
    buffer = io.StringIO()
    _write_criteria_header(buffer, review_project.criteria)
    extraction_fields = review_project.active_extraction_fields
    writer = csv.writer(buffer)
    writer.writerow([*CSV_HEADER, *(field.name for field in extraction_fields)])
    for citation in citations:
        writer.writerow(
            [
                citation.title,
                citation.abstract or "",
                "; ".join(citation.authors),
                citation.year or "",
                citation.source or "",
                citation.decision_label,
                citation.screening_reason,
                citation.ai_suggestion_decision_label,
                citation.ai_suggestion_reason_label,
                citation.full_text_decision_label,
                citation.full_text_reason_label,
                *(citation.extraction_value_for(field.id) for field in extraction_fields),
            ]
        )
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
