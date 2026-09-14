import csv
import io

from asr_backend import export
from asr_backend.ai_suggestion import SuggestionResult, get_ai_suggester
from asr_backend.main import app


class _FakeSuggester:
    def __init__(self, decision: str, reason: str) -> None:
        self.decision = decision
        self.reason = reason

    async def suggest_screening_decision(self, **kwargs) -> SuggestionResult:
        return SuggestionResult(decision=self.decision, reason=self.reason)


def create_project(client, name: str = "My Review") -> str:
    response = client.post("/review-projects", json={"name": name})
    return response.json()["id"]


def upload_csv(client, project_id: str, content: str):
    return client.post(
        f"/review-projects/{project_id}/citations",
        files={"file": ("citations.csv", content, "text/csv")},
    )


CSV_HEADER = "title,abstract,authors,year,source\n"


def parse_export(response) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(response.text)))


def generate_ai_suggestion(
    client, project_id: str, citation_id: str, decision: str = "include", reason: str = "Matches criteria."
) -> None:
    app.dependency_overrides[get_ai_suggester] = lambda: _FakeSuggester(
        decision=decision, reason=reason
    )
    try:
        client.get(f"/review-projects/{project_id}/citations/{citation_id}")
    finally:
        app.dependency_overrides.pop(get_ai_suggester, None)


def test_export_includes_screened_and_unscreened_citations(client):
    project_id = create_project(client)
    upload_csv(
        client,
        project_id,
        CSV_HEADER
        + "Screened Study,An abstract,Jane Doe; John Smith,2020,PubMed\n"
        + "Unscreened Study,Another abstract,Jane Doe,2021,PubMed\n",
    )
    citations = client.get(f"/review-projects/{project_id}/citations").json()
    screened_id = next(c["id"] for c in citations if c["title"] == "Screened Study")
    client.post(
        f"/review-projects/{project_id}/citations/{screened_id}/decision",
        json={"decision": "include", "reason": "Meets criteria"},
    )

    response = client.get(f"/review-projects/{project_id}/export")

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


def test_export_includes_ai_suggestion_columns_for_citation_with_suggestion(client):
    project_id = create_project(client)
    upload_csv(client, project_id, CSV_HEADER + "Study,An abstract,Author,2020,PubMed\n")
    citation_id = client.get(f"/review-projects/{project_id}/citations").json()[0]["id"]
    generate_ai_suggestion(
        client, project_id, citation_id, decision="exclude", reason="Wrong population."
    )

    response = client.get(f"/review-projects/{project_id}/export")

    row = parse_export(response)[0]
    assert row["ai_suggestion_decision"] == "exclude"
    assert row["ai_suggestion_reason"] == "Wrong population."


def test_export_marks_ai_suggestion_unavailable_when_none_generated(client):
    project_id = create_project(client)
    upload_csv(client, project_id, CSV_HEADER + "Study,An abstract,Author,2020,PubMed\n")

    response = client.get(f"/review-projects/{project_id}/export")

    row = parse_export(response)[0]
    assert row["ai_suggestion_decision"] == "not_available"
    assert row["ai_suggestion_reason"] == "not_available"


def test_export_marks_ai_suggestion_unavailable_for_citation_missing_abstract(client):
    project_id = create_project(client)
    upload_csv(client, project_id, CSV_HEADER + "Study,,Author,2020,PubMed\n")
    citation_id = client.get(f"/review-projects/{project_id}/citations").json()[0]["id"]
    generate_ai_suggestion(client, project_id, citation_id)

    response = client.get(f"/review-projects/{project_id}/export")

    row = parse_export(response)[0]
    assert row["ai_suggestion_decision"] == "not_available"
    assert row["ai_suggestion_reason"] == "not_available"


def test_export_shows_ai_suggestion_and_final_decision_when_they_disagree(client):
    project_id = create_project(client)
    upload_csv(client, project_id, CSV_HEADER + "Study,An abstract,Author,2020,PubMed\n")
    citation_id = client.get(f"/review-projects/{project_id}/citations").json()[0]["id"]
    generate_ai_suggestion(
        client, project_id, citation_id, decision="include", reason="Looks relevant."
    )
    client.post(
        f"/review-projects/{project_id}/citations/{citation_id}/decision",
        json={"decision": "exclude", "reason": "Reviewer disagrees"},
    )

    response = client.get(f"/review-projects/{project_id}/export")

    row = parse_export(response)[0]
    assert row["screening_decision"] == "exclude"
    assert row["reason"] == "Reviewer disagrees"
    assert row["ai_suggestion_decision"] == "include"
    assert row["ai_suggestion_reason"] == "Looks relevant."


def test_export_empty_review_project(client):
    project_id = create_project(client)

    response = client.get(f"/review-projects/{project_id}/export")

    assert response.status_code == 200
    assert parse_export(response) == []


def test_export_for_missing_review_project(client):
    response = client.get(
        "/review-projects/00000000-0000-0000-0000-000000000000/export"
    )

    assert response.status_code == 404


def test_export_filename_slugifies_project_name_and_appends_id_suffix(client):
    project_id = create_project(client, name="COPD & Metformin Review!!")

    response = client.get(f"/review-projects/{project_id}/export")

    disposition = response.headers["content-disposition"]
    assert f'filename="copd-metformin-review-{project_id[:8]}.csv"' in disposition


def save_criteria(client, project_id: str, **fields) -> None:
    payload = {
        "population": None,
        "intervention": None,
        "comparison": None,
        "outcome": None,
        "exclusion_rules": [],
        "notes": None,
    }
    payload.update(fields)
    response = client.put(f"/review-projects/{project_id}/criteria", json=payload)
    assert response.status_code == 200


def test_export_prepends_criteria_header_block_when_criteria_saved(client):
    project_id = create_project(client)
    save_criteria(
        client,
        project_id,
        population="Adults with type 2 diabetes",
        intervention="Metformin",
        comparison="Placebo",
        outcome="HbA1c reduction",
        exclusion_rules=["Non-English", "Case reports"],
        notes="Focus on RCTs only",
    )
    upload_csv(client, project_id, CSV_HEADER + "Study,An abstract,Author,2020,PubMed\n")

    response = client.get(f"/review-projects/{project_id}/export")

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


def test_export_criteria_header_block_renders_blank_for_unset_fields(client):
    project_id = create_project(client)
    save_criteria(client, project_id, notes="Only notes were filled in")

    response = client.get(f"/review-projects/{project_id}/export")

    lines = response.text.splitlines()
    assert lines[0] == "# Review Project Criteria"
    assert lines[1] == "# Population: "
    assert lines[2] == "# Intervention: "
    assert lines[3] == "# Comparison: "
    assert lines[4] == "# Outcome: "
    assert lines[5] == "# Exclusion Rules: "
    assert lines[6] == "# Notes: Only notes were filled in"
    assert lines[7] == ""


def test_export_omits_criteria_header_block_when_no_criteria_saved(client):
    project_id = create_project(client)

    response = client.get(f"/review-projects/{project_id}/export")

    lines = response.text.splitlines()
    assert lines[0] == ",".join(export.CSV_HEADER)
    assert not any(line.startswith("#") for line in lines)
