import csv
import io
import uuid

import pymupdf
import pytest
from conftest import auth_headers_for

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
        authed_client.post(f"/review-projects/{project_id}/citations/{citation_id}/suggestion")
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


def _create_dual_project(client, headers, name: str = "Dual Review") -> str:
    return client.post(
        "/review-projects",
        json={"name": name, "merge_mode": "combine", "review_mode": "dual"},
        headers=headers,
    ).json()["id"]


def _add_co_reviewer(client, owner_headers, project_id: str, email: str = "co-reviewer@example.com"):
    token = client.post(
        f"/review-projects/{project_id}/invitations", headers=owner_headers
    ).json()["token"]
    access_token = client.post(
        f"/invitations/{token}/accept-register",
        json={"email": email, "password": "correcthorse"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {access_token}"}


def _upload_citation(client, headers, project_id: str) -> str:
    client.post(
        f"/review-projects/{project_id}/citations",
        files={"file": ("citations.csv", CSV_HEADER + "Study,An abstract,Author,2020,PubMed\n", "text/csv")},
        headers=headers,
    )
    citations = client.get(f"/review-projects/{project_id}/citations", headers=headers).json()
    return citations[-1]["id"]


def _record_decision(client, project_id, citation_id, headers, decision, reason=None) -> None:
    client.post(
        f"/review-projects/{project_id}/citations/{citation_id}/decision",
        json={"decision": decision, "reason": reason},
        headers=headers,
    )


def _export_rows(client, project_id, headers) -> tuple[list[str], list[list[str]]]:
    response = client.get(f"/review-projects/{project_id}/export", headers=headers)
    lines = [line for line in response.text.splitlines() if line and not line.startswith("#")]
    header, *rows = lines
    return header.split(","), [row.split(",") for row in rows]


def test_export_dual_project_shows_matching_decisions_and_resolved_value_when_no_conflict(client):
    owner_headers = auth_headers_for(client, "owner@example.com")
    project_id = _create_dual_project(client, owner_headers)
    co_reviewer_headers = _add_co_reviewer(client, owner_headers, project_id)
    citation_id = _upload_citation(client, owner_headers, project_id)
    _record_decision(client, project_id, citation_id, owner_headers, "include", "Owner's take")
    _record_decision(client, project_id, citation_id, co_reviewer_headers, "include")

    header, rows = _export_rows(client, project_id, owner_headers)

    assert "owner_decision" in header
    assert "co_reviewer_decision" in header
    row = rows[0]
    assert row[header.index("owner_decision")] == "include"
    assert row[header.index("co_reviewer_decision")] == "include"
    assert row[header.index("screening_decision")] == "include"


def test_export_dual_project_shows_both_original_decisions_alongside_resolved_conflict(client):
    owner_headers = auth_headers_for(client, "owner@example.com")
    project_id = _create_dual_project(client, owner_headers)
    co_reviewer_headers = _add_co_reviewer(client, owner_headers, project_id)
    citation_id = _upload_citation(client, owner_headers, project_id)
    _record_decision(client, project_id, citation_id, owner_headers, "include")
    _record_decision(client, project_id, citation_id, co_reviewer_headers, "exclude")
    conflict_id = client.get(
        f"/review-projects/{project_id}/conflicts", headers=owner_headers
    ).json()[0]["id"]
    client.post(
        f"/review-projects/{project_id}/conflicts/{conflict_id}/resolve",
        json={"decision": "maybe", "reason": "Needs full text"},
        headers=owner_headers,
    )

    header, rows = _export_rows(client, project_id, owner_headers)

    row = rows[0]
    assert row[header.index("owner_decision")] == "include"
    assert row[header.index("co_reviewer_decision")] == "exclude"
    assert row[header.index("screening_decision")] == "maybe"


def test_export_solo_project_format_unchanged_by_dual_reviewer_columns(authed_client):
    project_id = create_project(authed_client)
    upload_csv(authed_client, project_id, CSV_HEADER + "Study,An abstract,Author,2020,PubMed\n")

    response = authed_client.get(f"/review-projects/{project_id}/export")

    lines = response.text.splitlines()
    assert lines[0] == ",".join(export.CSV_HEADER)
    assert "owner_decision" not in lines[0]
    assert "co_reviewer_decision" not in lines[0]


def test_export_joins_multiple_source_values_like_authors():
    project = models.ReviewProject(name="My Review")
    citation = models.Citation(
        title="Study",
        abstract="An abstract",
        authors=["Jane Doe"],
        year=2020,
        source=["PubMed", "Embase"],
    )

    csv_text = export.build_export_csv(project, [citation], requester=models.Reviewer(id=uuid.uuid4()))

    row = next(csv.DictReader(io.StringIO(csv_text)))
    assert row["source"] == "PubMed; Embase"


# --- Dual mode: per-citation blinding (#54, ADR 0006) -----------------------------------

BLINDED_COLUMNS = [
    "owner_decision",
    "co_reviewer_decision",
    "screening_decision",
    "reason",
    "ai_suggestion_decision",
    "ai_suggestion_reason",
]

# What a Solo export looked like before blinding existed; it must not change.
SOLO_FULL_EXPORT = (
    "# Review Project Criteria\r\n# Population: Adults\r\n# Intervention: \r\n"
    "# Comparison: \r\n# Outcome: \r\n# Exclusion Rules: wrong design\r\n# Notes: n\r\n\r\n"
    "title,abstract,authors,year,source,screening_decision,reason,ai_suggestion_decision,"
    "ai_suggestion_reason,full_text_decision,full_text_reason,Sample size\r\n"
    "Study A,An abstract,Jane Doe; John Smith,2020,PubMed,include,Human reason,exclude,"
    "AI reason,exclude,wrong design,120\r\n"
)
SOLO_BARE_EXPORT = (
    "title,abstract,authors,year,source,screening_decision,reason,ai_suggestion_decision,"
    "ai_suggestion_reason,full_text_decision,full_text_reason\r\n"
    "Study B,,Jane Doe,,PubMed,unscreened,,not_available,not_available,,\r\n"
)


def _upload_titled_citation(client, headers, project_id: str, title: str) -> str:
    client.post(
        f"/review-projects/{project_id}/citations",
        files={"file": ("c.csv", CSV_HEADER + f"{title},An abstract,Author,2020,PubMed\n", "text/csv")},
        headers=headers,
    )
    listed = client.get(f"/review-projects/{project_id}/citations", headers=headers).json()
    return next(c["id"] for c in listed if c["title"] == title)


def _generate_ai_suggestion_as(
    client, project_id, citation_id, headers, decision="exclude", reason="AI reason"
) -> None:
    app.dependency_overrides[get_ai_suggester] = lambda: _FakeSuggester(
        decision=decision, reason=reason
    )
    try:
        client.post(
            f"/review-projects/{project_id}/citations/{citation_id}/suggestion", headers=headers
        )
    finally:
        app.dependency_overrides.pop(get_ai_suggester, None)


def _export_records(client, project_id, headers) -> dict[str, dict[str, str]]:
    """The export's rows keyed by title, with the leading Criteria block skipped."""
    text = client.get(f"/review-projects/{project_id}/export", headers=headers).text
    lines = [line for line in text.splitlines() if not line.startswith("#")]
    return {row["title"]: row for row in csv.DictReader(io.StringIO("\n".join(lines)))}


def _dual_project_with_reviewers(client):
    owner_headers = auth_headers_for(client, "owner@example.com")
    project_id = _create_dual_project(client, owner_headers)
    co_reviewer_headers = _add_co_reviewer(client, owner_headers, project_id)
    return project_id, owner_headers, co_reviewer_headers


def test_a_reviewer_with_no_decision_gets_blanks_for_peer_final_and_ai_columns(client):
    project_id, owner_headers, co_reviewer_headers = _dual_project_with_reviewers(client)
    citation_id = _upload_titled_citation(client, owner_headers, project_id, "Study")
    _record_decision(client, project_id, citation_id, owner_headers, "include", "Owner's take")
    _generate_ai_suggestion_as(client, project_id, citation_id, owner_headers)

    row = _export_records(client, project_id, co_reviewer_headers)["Study"]

    assert {column: row[column] for column in BLINDED_COLUMNS} == dict.fromkeys(
        BLINDED_COLUMNS, ""
    )
    assert row["abstract"] == "An abstract"


def test_the_owner_with_no_decision_gets_blanks_when_the_co_reviewer_has_decided(client):
    project_id, owner_headers, co_reviewer_headers = _dual_project_with_reviewers(client)
    citation_id = _upload_titled_citation(client, owner_headers, project_id, "Study")
    _record_decision(client, project_id, citation_id, co_reviewer_headers, "exclude", "Their take")
    _generate_ai_suggestion_as(client, project_id, citation_id, co_reviewer_headers)

    row = _export_records(client, project_id, owner_headers)["Study"]

    assert {column: row[column] for column in BLINDED_COLUMNS} == dict.fromkeys(
        BLINDED_COLUMNS, ""
    )


def test_a_row_neither_reviewer_has_decided_hides_the_ai_suggestion_from_both(client):
    project_id, owner_headers, co_reviewer_headers = _dual_project_with_reviewers(client)
    citation_id = _upload_titled_citation(client, owner_headers, project_id, "Study")
    _generate_ai_suggestion_as(client, project_id, citation_id, owner_headers)

    for headers in (owner_headers, co_reviewer_headers):
        row = _export_records(client, project_id, headers)["Study"]
        assert row["ai_suggestion_decision"] == ""
        assert row["ai_suggestion_reason"] == ""
        assert row["screening_decision"] == ""


def test_a_reviewer_who_has_decided_sees_the_full_row(client):
    project_id, owner_headers, co_reviewer_headers = _dual_project_with_reviewers(client)
    citation_id = _upload_titled_citation(client, owner_headers, project_id, "Study")
    _record_decision(client, project_id, citation_id, owner_headers, "include", "Owner's take")
    _generate_ai_suggestion_as(client, project_id, citation_id, owner_headers, "exclude", "AI reason")
    _record_decision(client, project_id, citation_id, co_reviewer_headers, "include")

    for headers in (owner_headers, co_reviewer_headers):
        row = _export_records(client, project_id, headers)["Study"]
        assert row["owner_decision"] == "include"
        assert row["co_reviewer_decision"] == "include"
        assert row["screening_decision"] == "include"
        assert row["reason"] == "Owner's take"
        assert row["ai_suggestion_decision"] == "exclude"
        assert row["ai_suggestion_reason"] == "AI reason"


def test_deciding_a_citation_unblinds_that_row_for_the_reviewer_who_decided(client):
    project_id, owner_headers, co_reviewer_headers = _dual_project_with_reviewers(client)
    citation_id = _upload_titled_citation(client, owner_headers, project_id, "Study")
    _record_decision(client, project_id, citation_id, owner_headers, "include")
    assert _export_records(client, project_id, co_reviewer_headers)["Study"]["owner_decision"] == ""

    _record_decision(client, project_id, citation_id, co_reviewer_headers, "exclude")

    row = _export_records(client, project_id, co_reviewer_headers)["Study"]
    assert row["owner_decision"] == "include"
    assert row["co_reviewer_decision"] == "exclude"


def test_blinding_is_per_citation_not_per_reviewer(client):
    project_id, owner_headers, co_reviewer_headers = _dual_project_with_reviewers(client)
    decided_id = _upload_titled_citation(client, owner_headers, project_id, "Decided")
    open_id = _upload_titled_citation(client, owner_headers, project_id, "Open")
    _record_decision(client, project_id, decided_id, owner_headers, "include")
    _record_decision(client, project_id, open_id, owner_headers, "exclude")
    _record_decision(client, project_id, decided_id, co_reviewer_headers, "include")

    rows = _export_records(client, project_id, co_reviewer_headers)

    assert rows["Decided"]["owner_decision"] == "include"
    assert rows["Decided"]["screening_decision"] == "include"
    assert rows["Open"]["owner_decision"] == ""
    assert rows["Open"]["screening_decision"] == ""


def test_blinding_leaves_the_bibliographic_and_full_text_columns_alone(client):
    project_id, owner_headers, co_reviewer_headers = _dual_project_with_reviewers(client)
    citation_id = _upload_titled_citation(client, owner_headers, project_id, "Study")
    client.post(
        f"/review-projects/{project_id}/citations/{citation_id}/full-text",
        files={"file": ("paper.pdf", io.BytesIO(make_pdf()), "application/pdf")},
        headers=owner_headers,
    )
    client.post(
        f"/review-projects/{project_id}/citations/{citation_id}/full-text-decision",
        json={"decision": "include", "reason": "Fits"},
        headers=owner_headers,
    )

    row = _export_records(client, project_id, co_reviewer_headers)["Study"]

    assert (row["title"], row["authors"], row["year"], row["source"]) == (
        "Study",
        "Author",
        "2020",
        "PubMed",
    )
    assert (row["full_text_decision"], row["full_text_reason"]) == ("include", "Fits")


def test_a_pending_conflict_shows_both_decisions_to_a_reviewer_who_decided(client):
    project_id, owner_headers, co_reviewer_headers = _dual_project_with_reviewers(client)
    citation_id = _upload_titled_citation(client, owner_headers, project_id, "Study")
    _record_decision(client, project_id, citation_id, owner_headers, "include")
    _record_decision(client, project_id, citation_id, co_reviewer_headers, "exclude")

    row = _export_records(client, project_id, co_reviewer_headers)["Study"]

    assert (row["owner_decision"], row["co_reviewer_decision"]) == ("include", "exclude")


def test_solo_export_is_byte_for_byte_unchanged_with_every_column_filled(authed_client):
    project_id = create_project(authed_client)
    save_criteria(
        authed_client, project_id, population="Adults", exclusion_rules=["wrong design"], notes="n"
    )
    upload_csv(
        authed_client, project_id, CSV_HEADER + "Study A,An abstract,Jane Doe; John Smith,2020,PubMed\n"
    )
    citation_id = authed_client.get(f"/review-projects/{project_id}/citations").json()[0]["id"]
    generate_ai_suggestion(authed_client, project_id, citation_id, "exclude", "AI reason")
    authed_client.post(
        f"/review-projects/{project_id}/citations/{citation_id}/decision",
        json={"decision": "include", "reason": "Human reason"},
    )
    attach_full_text(authed_client, project_id, citation_id)
    record_full_text_decision(authed_client, project_id, citation_id, "exclude", "wrong design")
    field = create_extraction_field(authed_client, project_id, "Sample size")
    record_extraction_value(authed_client, project_id, citation_id, field["id"], "120")

    response = authed_client.get(f"/review-projects/{project_id}/export")

    assert response.text == SOLO_FULL_EXPORT


def test_solo_export_is_byte_for_byte_unchanged_for_an_undecided_citation(authed_client):
    project_id = create_project(authed_client)
    upload_csv(authed_client, project_id, CSV_HEADER + "Study B,,Jane Doe,,PubMed\n")

    response = authed_client.get(f"/review-projects/{project_id}/export")

    assert response.text == SOLO_BARE_EXPORT


# --- Spreadsheet formulas (#57) ------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        # Each prefix a spreadsheet reads as a formula gets a single quote.
        ("=1+1", "'=1+1"),
        ("+1", "'+1"),
        ("@SUM(A1)", "'@SUM(A1)"),
        ("\tcell", "'\tcell"),
        ("\rcell", "'\rcell"),
        # A minus does too, unless a digit follows it.
        ("-", "'-"),
        ("-abc", "'-abc"),
        ("--1", "'--1"),
        ("- 5", "'- 5"),
        ("-.5", "'-.5"),
        ("-²", "'-²"),
        # A negative number with an optional unit is a result, not a formula.
        ("-5", "-5"),
        ("-5 mmHg", "-5 mmHg"),
        ("-0.3", "-0.3"),
        ("-5mmHg", "-5mmHg"),
        ("-5 mg/dL", "-5 mg/dL"),
        ("-5%", "-5%"),
        ("-2.5 °C", "-2.5 °C"),
        ("-1,000 mL", "-1,000 mL"),
        ("-5 mm Hg", "-5 mm Hg"),
        # Anything else after the number gets the quote.
        ("-5+2", "'-5+2"),
        ("-5-2", "'-5-2"),
        ("-1 =2", "'-1 =2"),
        ("-5 to -2 mmHg", "'-5 to -2 mmHg"),
        ("-0.3 (95% CI -0.5 to -0.1)", "'-0.3 (95% CI -0.5 to -0.1)"),
        ("-5 A1", "'-5 A1"),
        ("-5 mm|x", "'-5 mm|x"),
        ("-5 mmHg ", "'-5 mmHg "),
        ("-5  mmHg", "'-5  mmHg"),
        ("-5\tmmHg", "'-5\tmmHg"),
        ("-5\nmmHg", "'-5\nmmHg"),
        ("-5\r", "'-5\r"),
        # Anything else passes through unchanged, including trigger characters
        # that are not first.
        ("", ""),
        ("Study", "Study"),
        ("5", "5"),
        ("a=b", "a=b"),
        ("x+y", "x+y"),
        ("x-y", "x-y"),
        ("email me @ home", "email me @ home"),
        (" =1+1", " =1+1"),
        ("# comment", "# comment"),
        # Not text: left alone (the year).
        (2020, 2020),
        (-5, -5),
    ],
)
def test_neutralize_cell(value, expected):
    assert export.neutralize_cell(value) == expected


def test_neutralize_cell_stays_fast_on_a_long_value_that_almost_matches():
    # A pattern that backtracks badly would hang here instead of failing.
    almost = "-5 " + "mmHg " * 20_000 + "!"

    assert export.neutralize_cell(almost) == "'" + almost


def test_export_neutralizes_formulas_in_every_text_column_and_the_header_row(authed_client):
    project_id = create_project(authed_client)
    field = create_extraction_field(authed_client, project_id, name="=cmd")
    upload_csv(
        authed_client,
        project_id,
        CSV_HEADER + "=title,+abstract,@author,2020,-source\n",
    )
    citation_id = authed_client.get(f"/review-projects/{project_id}/citations").json()[0]["id"]
    generate_ai_suggestion(authed_client, project_id, citation_id, "include", "=ai reason")
    authed_client.post(
        f"/review-projects/{project_id}/citations/{citation_id}/decision",
        json={"decision": "exclude", "reason": "+human reason"},
    )
    attach_full_text(authed_client, project_id, citation_id)
    record_full_text_decision(authed_client, project_id, citation_id, "exclude", "@full text reason")
    record_extraction_value(authed_client, project_id, citation_id, field["id"], "=1+1")

    response = authed_client.get(f"/review-projects/{project_id}/export")

    assert response.text.splitlines()[0].endswith(",'=cmd")
    row = parse_export(response)[0]
    assert row["title"] == "'=title"
    assert row["abstract"] == "'+abstract"
    assert row["authors"] == "'@author"
    assert row["source"] == "'-source"
    assert row["reason"] == "'+human reason"
    assert row["ai_suggestion_reason"] == "'=ai reason"
    assert row["full_text_reason"] == "'@full text reason"
    assert row["'=cmd"] == "'=1+1"
    # Numbers and clean text are untouched.
    assert row["year"] == "2020"
    assert row["screening_decision"] == "exclude"


def test_export_leaves_a_negative_number_in_an_extraction_value_as_is(authed_client):
    project_id = create_project(authed_client)
    field = create_extraction_field(authed_client, project_id, name="Change")
    upload_csv(authed_client, project_id, CSV_HEADER + "Study,An abstract,Author,2020,PubMed\n")
    citation_id = authed_client.get(f"/review-projects/{project_id}/citations").json()[0]["id"]
    record_extraction_value(authed_client, project_id, citation_id, field["id"], "-5 mmHg")

    response = authed_client.get(f"/review-projects/{project_id}/export")

    assert parse_export(response)[0]["Change"] == "-5 mmHg"


def test_export_criteria_block_stays_inert_when_a_value_has_line_breaks(authed_client):
    project_id = create_project(authed_client)
    save_criteria(
        authed_client,
        project_id,
        population="Adults\n=1+1",
        notes="first\r\n+second\r@third",
        exclusion_rules=["one\n-two", "plain"],
    )
    upload_csv(authed_client, project_id, CSV_HEADER + "Study,An abstract,Author,2020,PubMed\n")

    response = authed_client.get(f"/review-projects/{project_id}/export")

    lines = response.text.splitlines()
    block = lines[: lines.index("")]
    assert all(line.startswith("# ") for line in block)
    assert block == [
        "# Review Project Criteria",
        "# Population: Adults",
        "# =1+1",
        "# Intervention: ",
        "# Comparison: ",
        "# Outcome: ",
        "# Exclusion Rules: one",
        "# -two; plain",
        "# Notes: first",
        "# +second",
        "# @third",
    ]
    assert lines[len(block) + 1] == ",".join(export.CSV_HEADER)
