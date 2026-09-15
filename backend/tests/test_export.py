import csv
import io

import pymupdf

from asr_backend import export, models
from asr_backend.ai_suggestion import SuggestionResult, get_ai_suggester
from asr_backend.main import app


class _FakeSuggester:
    def __init__(self, decision: str, reason: str) -> None:
        self.decision = decision
        self.reason = reason

    async def suggest_screening_decision(self, **kwargs) -> SuggestionResult:
        return SuggestionResult(decision=self.decision, reason=self.reason)


def create_project(authed_client, name: str = "My Review") -> str:
    response = authed_client.post(
        "/review-projects",
        json={"name": name, "merge_mode": "combine", "review_mode": "solo"},
    )
    return response.json()["id"]


def upload_csv(authed_client, project_id: str, content: str):
    return authed_client.post(
        f"/review-projects/{project_id}/citations",
        files={"file": ("citations.csv", content, "text/csv")},
    )


CSV_HEADER = "title,abstract,authors,year,source\n"


def parse_export(response) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(response.text)))


def generate_ai_suggestion(
    authed_client, project_id: str, citation_id: str, decision: str = "include", reason: str = "Matches criteria."
) -> None:
    app.dependency_overrides[get_ai_suggester] = lambda: _FakeSuggester(
        decision=decision, reason=reason
    )
    try:
        authed_client.get(f"/review-projects/{project_id}/citations/{citation_id}")
    finally:
        app.dependency_overrides.pop(get_ai_suggester, None)


def test_export_includes_screened_and_unscreened_citations(authed_client):
    project_id = create_project(authed_client)
    upload_csv(
        authed_client,
        project_id,
        CSV_HEADER
        + "Screened Study,An abstract,Jane Doe; John Smith,2020,PubMed\n"
        + "Unscreened Study,Another abstract,Jane Doe,2021,PubMed\n",
    )
    citations = authed_client.get(f"/review-projects/{project_id}/citations").json()
    screened_id = next(c["id"] for c in citations if c["title"] == "Screened Study")
    authed_client.post(
        f"/review-projects/{project_id}/citations/{screened_id}/decision",
        json={"decision": "include", "reason": "Meets criteria"},
    )

    response = authed_client.get(f"/review-projects/{project_id}/export")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    rows = parse_export(response)
    assert len(rows) == 2

    screened_row = next(row for row in rows if row["title"] == "Screened Study")
    assert screened_row["abstract"] == "An abstract"
    assert screened_row["authors"] == "Jane Doe; John Smith"
    assert screened_row["year"] == "2020"
    assert screened_row["source"] == "PubMed"
    assert screened_row["screening_decision"] == "include"
    assert screened_row["reason"] == "Meets criteria"

    unscreened_row = next(row for row in rows if row["title"] == "Unscreened Study")
    assert unscreened_row["screening_decision"] == "unscreened"
    assert unscreened_row["reason"] == ""


def test_export_includes_ai_suggestion_columns_for_citation_with_suggestion(authed_client):
    project_id = create_project(authed_client)
    upload_csv(authed_client, project_id, CSV_HEADER + "Study,An abstract,Author,2020,PubMed\n")
    citation_id = authed_client.get(f"/review-projects/{project_id}/citations").json()[0]["id"]
    generate_ai_suggestion(
        authed_client, project_id, citation_id, decision="exclude", reason="Wrong population."
    )

    response = authed_client.get(f"/review-projects/{project_id}/export")

    row = parse_export(response)[0]
    assert row["ai_suggestion_decision"] == "exclude"
    assert row["ai_suggestion_reason"] == "Wrong population."


def test_export_marks_ai_suggestion_unavailable_when_none_generated(authed_client):
    project_id = create_project(authed_client)
    upload_csv(authed_client, project_id, CSV_HEADER + "Study,An abstract,Author,2020,PubMed\n")

    response = authed_client.get(f"/review-projects/{project_id}/export")

    row = parse_export(response)[0]
    assert row["ai_suggestion_decision"] == "not_available"
    assert row["ai_suggestion_reason"] == "not_available"


def test_export_marks_ai_suggestion_unavailable_for_citation_missing_abstract(authed_client):
    project_id = create_project(authed_client)
    upload_csv(authed_client, project_id, CSV_HEADER + "Study,,Author,2020,PubMed\n")
    citation_id = authed_client.get(f"/review-projects/{project_id}/citations").json()[0]["id"]
    generate_ai_suggestion(authed_client, project_id, citation_id)

    response = authed_client.get(f"/review-projects/{project_id}/export")

    row = parse_export(response)[0]
    assert row["ai_suggestion_decision"] == "not_available"
    assert row["ai_suggestion_reason"] == "not_available"


def test_export_shows_ai_suggestion_and_final_decision_when_they_disagree(authed_client):
    project_id = create_project(authed_client)
    upload_csv(authed_client, project_id, CSV_HEADER + "Study,An abstract,Author,2020,PubMed\n")
    citation_id = authed_client.get(f"/review-projects/{project_id}/citations").json()[0]["id"]
    generate_ai_suggestion(
        authed_client, project_id, citation_id, decision="include", reason="Looks relevant."
    )
    authed_client.post(
        f"/review-projects/{project_id}/citations/{citation_id}/decision",
        json={"decision": "exclude", "reason": "Reviewer disagrees"},
    )

    response = authed_client.get(f"/review-projects/{project_id}/export")

    row = parse_export(response)[0]
    assert row["screening_decision"] == "exclude"
    assert row["reason"] == "Reviewer disagrees"
    assert row["ai_suggestion_decision"] == "include"
    assert row["ai_suggestion_reason"] == "Looks relevant."


def make_pdf(text: str = "Sample paper text") -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    return doc.tobytes()


def attach_full_text(authed_client, project_id: str, citation_id: str) -> None:
    authed_client.post(
        f"/review-projects/{project_id}/citations/{citation_id}/full-text",
        files={"file": ("paper.pdf", io.BytesIO(make_pdf()), "application/pdf")},
    )


def record_full_text_decision(
    authed_client, project_id: str, citation_id: str, decision: str, reason: str | None = None
) -> None:
    authed_client.post(
        f"/review-projects/{project_id}/citations/{citation_id}/full-text-decision",
        json={"decision": decision, "reason": reason},
    )


def create_extraction_field(authed_client, project_id: str, name: str = "Sample size") -> dict:
    return authed_client.post(
        f"/review-projects/{project_id}/extraction-fields",
        json={"name": name, "description": None},
    ).json()


def archive_extraction_field(authed_client, project_id: str, field_id: str) -> None:
    authed_client.post(f"/review-projects/{project_id}/extraction-fields/{field_id}/archive")


def record_extraction_value(authed_client, project_id: str, citation_id: str, field_id: str, value: str) -> None:
    authed_client.post(
        f"/review-projects/{project_id}/citations/{citation_id}"
        f"/extraction-fields/{field_id}/value",
        json={"value": value},
    )


def test_export_includes_full_text_decision_and_reason_when_recorded(authed_client):
    project_id = create_project(authed_client)
    upload_csv(authed_client, project_id, CSV_HEADER + "Study,An abstract,Author,2020,PubMed\n")
    citation_id = authed_client.get(f"/review-projects/{project_id}/citations").json()[0]["id"]
    attach_full_text(authed_client, project_id, citation_id)
    record_full_text_decision(
        authed_client, project_id, citation_id, "exclude", "Wrong study design on closer read"
    )

    response = authed_client.get(f"/review-projects/{project_id}/export")

    row = parse_export(response)[0]
    assert row["full_text_decision"] == "exclude"
    assert row["full_text_reason"] == "Wrong study design on closer read"


def test_export_full_text_reason_empty_when_decision_recorded_without_reason(authed_client):
    project_id = create_project(authed_client)
    upload_csv(authed_client, project_id, CSV_HEADER + "Study,An abstract,Author,2020,PubMed\n")
    citation_id = authed_client.get(f"/review-projects/{project_id}/citations").json()[0]["id"]
    attach_full_text(authed_client, project_id, citation_id)
    record_full_text_decision(authed_client, project_id, citation_id, "include")

    response = authed_client.get(f"/review-projects/{project_id}/export")

    row = parse_export(response)[0]
    assert row["full_text_decision"] == "include"
    assert row["full_text_reason"] == ""


def test_export_full_text_decision_columns_empty_when_no_decision_recorded(authed_client):
    project_id = create_project(authed_client)
    upload_csv(authed_client, project_id, CSV_HEADER + "Study,An abstract,Author,2020,PubMed\n")

    response = authed_client.get(f"/review-projects/{project_id}/export")

    row = parse_export(response)[0]
    assert row["full_text_decision"] == ""
    assert row["full_text_reason"] == ""


def test_export_includes_column_per_active_extraction_field_with_recorded_value(authed_client):
    project_id = create_project(authed_client)
    field = create_extraction_field(authed_client, project_id, name="Sample size")
    upload_csv(authed_client, project_id, CSV_HEADER + "Study,An abstract,Author,2020,PubMed\n")
    citation_id = authed_client.get(f"/review-projects/{project_id}/citations").json()[0]["id"]
    record_extraction_value(authed_client, project_id, citation_id, field["id"], "142 patients")

    response = authed_client.get(f"/review-projects/{project_id}/export")

    lines = response.text.splitlines()
    assert lines[0] == ",".join([*export.CSV_HEADER, "Sample size"])
    row = parse_export(response)[0]
    assert row["Sample size"] == "142 patients"


def test_export_extraction_field_column_empty_when_no_value_recorded(authed_client):
    project_id = create_project(authed_client)
    create_extraction_field(authed_client, project_id, name="Sample size")
    upload_csv(authed_client, project_id, CSV_HEADER + "Study,An abstract,Author,2020,PubMed\n")

    response = authed_client.get(f"/review-projects/{project_id}/export")

    row = parse_export(response)[0]
    assert row["Sample size"] == ""


def test_export_omits_archived_extraction_fields_from_columns(authed_client):
    project_id = create_project(authed_client)
    field = create_extraction_field(authed_client, project_id, name="Sample size")
    archive_extraction_field(authed_client, project_id, field["id"])
    upload_csv(authed_client, project_id, CSV_HEADER + "Study,An abstract,Author,2020,PubMed\n")

    response = authed_client.get(f"/review-projects/{project_id}/export")

    lines = response.text.splitlines()
    assert lines[0] == ",".join(export.CSV_HEADER)
    assert "Sample size" not in lines[0]


def test_export_empty_review_project(authed_client):
    project_id = create_project(authed_client)

    response = authed_client.get(f"/review-projects/{project_id}/export")

    assert response.status_code == 200
    assert parse_export(response) == []


def test_export_for_missing_review_project(authed_client):
    response = authed_client.get(
        "/review-projects/00000000-0000-0000-0000-000000000000/export"
    )

    assert response.status_code == 404


def test_export_filename_slugifies_project_name_and_appends_id_suffix(authed_client):
    project_id = create_project(authed_client, name="COPD & Metformin Review!!")

    response = authed_client.get(f"/review-projects/{project_id}/export")

    disposition = response.headers["content-disposition"]
    assert f'filename="copd-metformin-review-{project_id[:8]}.csv"' in disposition


def save_criteria(authed_client, project_id: str, **fields) -> None:
    payload = {
        "population": None,
        "intervention": None,
        "comparison": None,
        "outcome": None,
        "exclusion_rules": [],
        "notes": None,
    }
    payload.update(fields)
    response = authed_client.put(f"/review-projects/{project_id}/criteria", json=payload)
    assert response.status_code == 200


def test_export_prepends_criteria_header_block_when_criteria_saved(authed_client):
    project_id = create_project(authed_client)
    save_criteria(
        authed_client,
        project_id,
        population="Adults with type 2 diabetes",
        intervention="Metformin",
        comparison="Placebo",
        outcome="HbA1c reduction",
        exclusion_rules=["Non-English", "Case reports"],
        notes="Focus on RCTs only",
    )
    upload_csv(authed_client, project_id, CSV_HEADER + "Study,An abstract,Author,2020,PubMed\n")

    response = authed_client.get(f"/review-projects/{project_id}/export")

    lines = response.text.splitlines()
    assert lines[0] == "# Review Project Criteria"
    assert lines[1] == "# Population: Adults with type 2 diabetes"
    assert lines[2] == "# Intervention: Metformin"
    assert lines[3] == "# Comparison: Placebo"
    assert lines[4] == "# Outcome: HbA1c reduction"
    assert lines[5] == "# Exclusion Rules: Non-English; Case reports"
    assert lines[6] == "# Notes: Focus on RCTs only"
    assert lines[7] == ""
    assert lines[8] == ",".join(export.CSV_HEADER)

    rows = list(csv.DictReader(io.StringIO("\n".join(lines[8:]))))
    assert len(rows) == 1
    assert rows[0]["title"] == "Study"


def test_export_criteria_header_block_renders_blank_for_unset_fields(authed_client):
    project_id = create_project(authed_client)
    save_criteria(authed_client, project_id, notes="Only notes were filled in")

    response = authed_client.get(f"/review-projects/{project_id}/export")

    lines = response.text.splitlines()
    assert lines[0] == "# Review Project Criteria"
    assert lines[1] == "# Population: "
    assert lines[2] == "# Intervention: "
    assert lines[3] == "# Comparison: "
    assert lines[4] == "# Outcome: "
    assert lines[5] == "# Exclusion Rules: "
    assert lines[6] == "# Notes: Only notes were filled in"
    assert lines[7] == ""


def test_export_omits_criteria_header_block_when_no_criteria_saved(authed_client):
    project_id = create_project(authed_client)

    response = authed_client.get(f"/review-projects/{project_id}/export")

    lines = response.text.splitlines()
    assert lines[0] == ",".join(export.CSV_HEADER)
    assert not any(line.startswith("#") for line in lines)


def test_export_joins_multiple_source_values_like_authors():
    project = models.ReviewProject(name="My Review")
    citation = models.Citation(
        title="Study",
        abstract="An abstract",
        authors=["Jane Doe"],
        year=2020,
        source=["PubMed", "Embase"],
    )

    csv_text = export.build_export_csv(project, [citation])

    row = next(csv.DictReader(io.StringIO(csv_text)))
    assert row["source"] == "PubMed; Embase"
