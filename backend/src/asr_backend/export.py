import csv
import io

from asr_backend import models

CSV_HEADER = ["title", "abstract", "authors", "year", "source", "decision"]


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
            ]
        )
    return buffer.getvalue()
