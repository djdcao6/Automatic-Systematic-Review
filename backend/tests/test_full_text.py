import io

import pymupdf

from asr_backend import full_text


def create_project(authed_client, name: str = "My Review") -> str:
    response = authed_client.post("/review-projects", json={"name": name, "merge_mode": "combine"})
    return response.json()["id"]


def create_citation(authed_client, project_id: str, title: str = "Study A") -> str:
    authed_client.post(
        f"/review-projects/{project_id}/citations",
        files={
            "file": (
                "citations.csv",
                f"title,abstract,authors,year,source\n{title},An abstract,Jane Doe,2020,PubMed\n",
                "text/csv",
            )
        },
    )
    citations = authed_client.get(f"/review-projects/{project_id}/citations").json()
    return next(c["id"] for c in citations if c["title"] == title)


def make_pdf(text: str | None = "Sample paper text") -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    if text:
        page.insert_text((72, 72), text)
    return doc.tobytes()


def upload_full_text(authed_client, project_id: str, citation_id: str, content: bytes, filename="paper.pdf"):
    return authed_client.post(
        f"/review-projects/{project_id}/citations/{citation_id}/full-text",
        files={"file": (filename, io.BytesIO(content), "application/pdf")},
    )


def test_upload_full_text_parses_and_stores_pdf(authed_client):
    project_id = create_project(authed_client)
    citation_id = create_citation(authed_client, project_id)

    response = upload_full_text(authed_client, project_id, citation_id, make_pdf("Hello world"))

    assert response.status_code == 201
    body = response.json()
    assert body["original_filename"] == "paper.pdf"
    assert body["parse_status"] == "parsed"

    detail = authed_client.get(f"/review-projects/{project_id}/citations/{citation_id}").json()
    assert detail["full_text"]["parse_status"] == "parsed"
    assert detail["full_text"]["original_filename"] == "paper.pdf"


def test_full_text_can_be_attached_regardless_of_screening_decision(authed_client):
    project_id = create_project(authed_client)
    citation_id = create_citation(authed_client, project_id)
    authed_client.post(
        f"/review-projects/{project_id}/citations/{citation_id}/decision",
        json={"decision": "exclude", "reason": "wrong population"},
    )

    response = upload_full_text(authed_client, project_id, citation_id, make_pdf())

    assert response.status_code == 201


def test_pdf_with_no_text_layer_is_flagged_not_errored(authed_client):
    project_id = create_project(authed_client)
    citation_id = create_citation(authed_client, project_id)

    response = upload_full_text(authed_client, project_id, citation_id, make_pdf(text=None))

    assert response.status_code == 201
    assert response.json()["parse_status"] == "parse_failed"

    citations = authed_client.get(f"/review-projects/{project_id}/citations").json()
    assert len(citations) == 1


def test_uploading_again_replaces_the_previous_full_text(authed_client):
    project_id = create_project(authed_client)
    citation_id = create_citation(authed_client, project_id)

    upload_full_text(authed_client, project_id, citation_id, make_pdf("First version"), filename="v1.pdf")
    second = upload_full_text(
        authed_client, project_id, citation_id, make_pdf("Second version"), filename="v2.pdf"
    )

    assert second.status_code == 201
    assert second.json()["original_filename"] == "v2.pdf"

    detail = authed_client.get(f"/review-projects/{project_id}/citations/{citation_id}").json()
    assert detail["full_text"]["original_filename"] == "v2.pdf"

    download = authed_client.get(
        f"/review-projects/{project_id}/citations/{citation_id}/full-text/file"
    )
    assert download.status_code == 200
    downloaded_text, _ = full_text.extract_text(download.content)
    assert downloaded_text == "Second version"


def test_replacing_a_parsed_full_text_with_an_unparseable_one_flags_it(authed_client):
    project_id = create_project(authed_client)
    citation_id = create_citation(authed_client, project_id)

    upload_full_text(authed_client, project_id, citation_id, make_pdf("Readable text"))
    second = upload_full_text(authed_client, project_id, citation_id, make_pdf(text=None))

    assert second.status_code == 201
    assert second.json()["parse_status"] == "parse_failed"

    detail = authed_client.get(f"/review-projects/{project_id}/citations/{citation_id}").json()
    assert detail["full_text"]["parse_status"] == "parse_failed"


def test_download_full_text_returns_the_uploaded_pdf(authed_client):
    project_id = create_project(authed_client)
    citation_id = create_citation(authed_client, project_id)
    pdf_bytes = make_pdf("Downloadable content")
    upload_full_text(authed_client, project_id, citation_id, pdf_bytes)

    response = authed_client.get(
        f"/review-projects/{project_id}/citations/{citation_id}/full-text/file"
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content == pdf_bytes


def test_download_full_text_returns_404_when_none_uploaded(authed_client):
    project_id = create_project(authed_client)
    citation_id = create_citation(authed_client, project_id)

    response = authed_client.get(
        f"/review-projects/{project_id}/citations/{citation_id}/full-text/file"
    )

    assert response.status_code == 404


def test_citation_detail_has_no_full_text_before_upload(authed_client):
    project_id = create_project(authed_client)
    citation_id = create_citation(authed_client, project_id)

    detail = authed_client.get(f"/review-projects/{project_id}/citations/{citation_id}").json()

    assert detail["full_text"] is None


def test_upload_full_text_rejects_non_pdf_file(authed_client):
    project_id = create_project(authed_client)
    citation_id = create_citation(authed_client, project_id)

    response = authed_client.post(
        f"/review-projects/{project_id}/citations/{citation_id}/full-text",
        files={"file": ("notes.txt", b"not a pdf", "text/plain")},
    )

    assert response.status_code == 422


def test_upload_full_text_for_missing_citation_returns_404(authed_client):
    project_id = create_project(authed_client)

    response = authed_client.post(
        f"/review-projects/{project_id}/citations/00000000-0000-0000-0000-000000000000/full-text",
        files={"file": ("paper.pdf", io.BytesIO(make_pdf()), "application/pdf")},
    )

    assert response.status_code == 404
