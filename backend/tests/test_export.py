import csv
import io


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
