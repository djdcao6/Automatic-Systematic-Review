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
]

_SLUG_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def slugify(value: str) -> str:
    slug = _SLUG_NON_ALNUM.sub("-", value.lower()).strip("-")
    return slug or "review-project"


def build_export_filename(review_project: models.ReviewProject) -> str:
    id_suffix = str(review_project.id).split("-")[0]
    return f"{slugify(review_project.name)}-{id_suffix}.csv"


def build_citations_csv(citations: list[models.Citation]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(CSV_HEADER)
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
            ]
        )
    return buffer.getvalue()
