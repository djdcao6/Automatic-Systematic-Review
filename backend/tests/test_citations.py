def create_project(authed_client, name: str = "My Review") -> str:
    response = authed_client.post(
        "/review-projects",
        json={"name": name, "merge_mode": "combine", "review_mode": "solo"},
    )
    return response.json()["id"]


def upload_csv(authed_client, project_id: str, content: str, filename: str = "citations.csv"):
    return authed_client.post(
        f"/review-projects/{project_id}/citations",
        files={"file": (filename, content, "text/csv")},
    )


def upload_ris(authed_client, project_id: str, content: str, filename: str = "citations.ris"):
    return authed_client.post(
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


def test_upload_csv_citations(authed_client):
    project_id = create_project(authed_client)

    response = upload_csv(
        authed_client,
        project_id,
        CSV_HEADER + "Study A,An abstract,Jane Doe; John Smith,2020,PubMed\n",
    )

    assert response.status_code == 201
    assert response.json() == {"created": 1, "skipped": []}

    citations = authed_client.get(f"/review-projects/{project_id}/citations").json()
    assert len(citations) == 1
    assert citations[0]["title"] == "Study A"
    assert citations[0]["abstract"] == "An abstract"
    assert citations[0]["authors"] == ["Jane Doe", "John Smith"]
    assert citations[0]["year"] == 2020
    assert citations[0]["source"] == ["PubMed"]
    assert citations[0]["needs_abstract"] is False


def test_upload_csv_with_missing_source_is_an_empty_list(authed_client):
    project_id = create_project(authed_client)

    upload_csv(authed_client, project_id, CSV_HEADER + "Study A,An abstract,Jane Doe,2020,\n")

    citations = authed_client.get(f"/review-projects/{project_id}/citations").json()
    assert citations[0]["source"] == []


def test_upload_csv_with_missing_abstract_flags_not_drops(authed_client):
    project_id = create_project(authed_client)

    upload_csv(authed_client, project_id, CSV_HEADER + "Study B,,Jane Doe,2021,PubMed\n")

    citations = authed_client.get(f"/review-projects/{project_id}/citations").json()
    assert len(citations) == 1
    assert citations[0]["abstract"] is None
    assert citations[0]["needs_abstract"] is True


def test_upload_csv_skips_row_missing_title(authed_client):
    project_id = create_project(authed_client)

    response = upload_csv(
        authed_client,
        project_id,
        CSV_HEADER
        + ",An abstract,Jane Doe,2020,PubMed\n"
        + "Good Study,Another abstract,John Smith,2021,PubMed\n",
    )

    body = response.json()
    assert body["created"] == 1
    assert body["skipped"] == [{"row": 1, "reason": "missing title"}]


def test_uploading_again_appends_citations(authed_client):
    project_id = create_project(authed_client)

    upload_csv(authed_client, project_id, CSV_HEADER + "First,Abstract,Author,2020,PubMed\n")
    upload_csv(authed_client, project_id, CSV_HEADER + "Second,Abstract,Author,2021,PubMed\n")

    citations = authed_client.get(f"/review-projects/{project_id}/citations").json()
    assert [c["title"] for c in citations] == ["First", "Second"]


def test_duplicate_rows_in_same_batch_are_created_then_merged(authed_client):
    """As of ticket #20, matching title-duplicate rows collapse into one
    surviving Citation (see test_duplicates.py) rather than staying
    independent, overturning the "no deduplication" design from #4."""
    project_id = create_project(authed_client)

    response = upload_csv(
        authed_client,
        project_id,
        CSV_HEADER
        + "Dup,Abstract,Author,2020,PubMed\n"
        + "Dup,Abstract,Author,2020,PubMed\n",
    )

    assert response.json()["created"] == 2
    citations = authed_client.get(f"/review-projects/{project_id}/citations").json()
    assert len(citations) == 1


def test_upload_ris_citations(authed_client):
    project_id = create_project(authed_client)

    response = upload_ris(authed_client, project_id, RIS_SAMPLE)

    assert response.status_code == 201
    assert response.json() == {"created": 1, "skipped": []}

    citations = authed_client.get(f"/review-projects/{project_id}/citations").json()
    assert citations[0]["title"] == "RIS Study"
    assert citations[0]["abstract"] == "An RIS abstract"
    assert citations[0]["authors"] == ["Doe, Jane", "Smith, John"]
    assert citations[0]["year"] == 2019
    assert citations[0]["source"] == ["PubMed"]


def test_upload_ris_skips_entry_missing_title(authed_client):
    project_id = create_project(authed_client)

    response = upload_ris(authed_client, project_id, RIS_MISSING_TITLE)

    body = response.json()
    assert body["created"] == 0
    assert body["skipped"] == [{"row": 1, "reason": "missing title"}]


def test_upload_ris_with_missing_abstract_flags_not_drops(authed_client):
    project_id = create_project(authed_client)

    upload_ris(authed_client, project_id, RIS_MISSING_ABSTRACT)

    citations = authed_client.get(f"/review-projects/{project_id}/citations").json()
    assert len(citations) == 1
    assert citations[0]["needs_abstract"] is True


def test_upload_rejects_unsupported_file_type(authed_client):
    project_id = create_project(authed_client)

    response = authed_client.post(
        f"/review-projects/{project_id}/citations",
        files={"file": ("notes.txt", "not a real citation file", "text/plain")},
    )

    assert response.status_code == 422


def test_upload_rejects_non_utf8_file(authed_client):
    project_id = create_project(authed_client)
    non_utf8_content = "café".encode("latin-1")

    response = authed_client.post(
        f"/review-projects/{project_id}/citations",
        files={"file": ("citations.csv", non_utf8_content, "text/csv")},
    )

    assert response.status_code == 422


def test_upload_citations_for_missing_review_project(authed_client):
    response = authed_client.post(
        "/review-projects/00000000-0000-0000-0000-000000000000/citations",
        files={"file": ("c.csv", CSV_HEADER + "X,Abstract,Author,2020,PubMed\n", "text/csv")},
    )

    assert response.status_code == 404


def test_list_citations_for_missing_review_project(authed_client):
    response = authed_client.get("/review-projects/00000000-0000-0000-0000-000000000000/citations")

    assert response.status_code == 404


def test_list_citations_empty(authed_client):
    project_id = create_project(authed_client)

    response = authed_client.get(f"/review-projects/{project_id}/citations")

    assert response.status_code == 200
    assert response.json() == []
