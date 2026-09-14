def create_project(client, name: str = "My Review") -> str:
    response = client.post("/review-projects", json={"name": name})
    return response.json()["id"]


def upload_csv(client, project_id: str, content: str, filename: str = "citations.csv"):
    return client.post(
        f"/review-projects/{project_id}/citations",
        files={"file": (filename, content, "text/csv")},
    )


def upload_ris(client, project_id: str, content: str, filename: str = "citations.ris"):
    return client.post(
        f"/review-projects/{project_id}/citations",
        files={"file": (filename, content, "application/x-research-info-systems")},
    )


CSV_HEADER = "title,abstract,authors,year,source\n"

RIS_SAMPLE = (
    "TY  - JOUR\n"
    "TI  - RIS Study\n"
    "AB  - An RIS abstract\n"
    "AU  - Doe, Jane\n"
    "AU  - Smith, John\n"
    "PY  - 2019\n"
    "DB  - PubMed\n"
    "ER  - \n"
)

RIS_MISSING_TITLE = "TY  - JOUR\nAB  - No title here\nPY  - 2020\nER  - \n"

RIS_MISSING_ABSTRACT = (
    "TY  - JOUR\nTI  - RIS No Abstract\nAU  - Doe, Jane\nPY  - 2021\nER  - \n"
)


def test_upload_csv_citations(client):
    project_id = create_project(client)

    response = upload_csv(
        client,
        project_id,
        CSV_HEADER + "Study A,An abstract,Jane Doe; John Smith,2020,PubMed\n",
    )

    assert response.status_code == 201
    assert response.json() == {"created": 1, "skipped": []}

    citations = client.get(f"/review-projects/{project_id}/citations").json()
    assert len(citations) == 1
    assert citations[0]["title"] == "Study A"
    assert citations[0]["abstract"] == "An abstract"
    assert citations[0]["authors"] == ["Jane Doe", "John Smith"]
    assert citations[0]["year"] == 2020
    assert citations[0]["source"] == ["PubMed"]
    assert citations[0]["needs_abstract"] is False


def test_upload_csv_with_missing_source_is_an_empty_list(client):
    project_id = create_project(client)

    upload_csv(client, project_id, CSV_HEADER + "Study A,An abstract,Jane Doe,2020,\n")

    citations = client.get(f"/review-projects/{project_id}/citations").json()
    assert citations[0]["source"] == []


def test_upload_csv_with_missing_abstract_flags_not_drops(client):
    project_id = create_project(client)

    upload_csv(client, project_id, CSV_HEADER + "Study B,,Jane Doe,2021,PubMed\n")

    citations = client.get(f"/review-projects/{project_id}/citations").json()
    assert len(citations) == 1
    assert citations[0]["abstract"] is None
    assert citations[0]["needs_abstract"] is True


def test_upload_csv_skips_row_missing_title(client):
    project_id = create_project(client)

    response = upload_csv(
        client,
        project_id,
        CSV_HEADER
        + ",An abstract,Jane Doe,2020,PubMed\n"
        + "Good Study,Another abstract,John Smith,2021,PubMed\n",
    )

    body = response.json()
    assert body["created"] == 1
    assert body["skipped"] == [{"row": 1, "reason": "missing title"}]


def test_uploading_again_appends_citations(client):
    project_id = create_project(client)

    upload_csv(client, project_id, CSV_HEADER + "First,Abstract,Author,2020,PubMed\n")
    upload_csv(client, project_id, CSV_HEADER + "Second,Abstract,Author,2021,PubMed\n")

    citations = client.get(f"/review-projects/{project_id}/citations").json()
    assert [c["title"] for c in citations] == ["First", "Second"]


def test_duplicate_rows_are_each_created_independently(client):
    project_id = create_project(client)

    response = upload_csv(
        client,
        project_id,
        CSV_HEADER
        + "Dup,Abstract,Author,2020,PubMed\n"
        + "Dup,Abstract,Author,2020,PubMed\n",
    )

    assert response.json()["created"] == 2
    citations = client.get(f"/review-projects/{project_id}/citations").json()
    assert len(citations) == 2


def test_upload_ris_citations(client):
    project_id = create_project(client)

    response = upload_ris(client, project_id, RIS_SAMPLE)

    assert response.status_code == 201
    assert response.json() == {"created": 1, "skipped": []}

    citations = client.get(f"/review-projects/{project_id}/citations").json()
    assert citations[0]["title"] == "RIS Study"
    assert citations[0]["abstract"] == "An RIS abstract"
    assert citations[0]["authors"] == ["Doe, Jane", "Smith, John"]
    assert citations[0]["year"] == 2019
    assert citations[0]["source"] == ["PubMed"]


def test_upload_ris_skips_entry_missing_title(client):
    project_id = create_project(client)

    response = upload_ris(client, project_id, RIS_MISSING_TITLE)

    body = response.json()
    assert body["created"] == 0
    assert body["skipped"] == [{"row": 1, "reason": "missing title"}]


def test_upload_ris_with_missing_abstract_flags_not_drops(client):
    project_id = create_project(client)

    upload_ris(client, project_id, RIS_MISSING_ABSTRACT)

    citations = client.get(f"/review-projects/{project_id}/citations").json()
    assert len(citations) == 1
    assert citations[0]["needs_abstract"] is True


def test_upload_rejects_unsupported_file_type(client):
    project_id = create_project(client)

    response = client.post(
        f"/review-projects/{project_id}/citations",
        files={"file": ("notes.txt", "not a real citation file", "text/plain")},
    )

    assert response.status_code == 422


def test_upload_rejects_non_utf8_file(client):
    project_id = create_project(client)
    non_utf8_content = "café".encode("latin-1")

    response = client.post(
        f"/review-projects/{project_id}/citations",
        files={"file": ("citations.csv", non_utf8_content, "text/csv")},
    )

    assert response.status_code == 422


def test_upload_citations_for_missing_review_project(client):
    response = client.post(
        "/review-projects/00000000-0000-0000-0000-000000000000/citations",
        files={"file": ("c.csv", CSV_HEADER + "X,Abstract,Author,2020,PubMed\n", "text/csv")},
    )

    assert response.status_code == 404


def test_list_citations_for_missing_review_project(client):
    response = client.get("/review-projects/00000000-0000-0000-0000-000000000000/citations")

    assert response.status_code == 404


def test_list_citations_empty(client):
    project_id = create_project(client)

    response = client.get(f"/review-projects/{project_id}/citations")

    assert response.status_code == 200
    assert response.json() == []
