"""Upload size limits and keeping upload parsing off the event loop (#55)."""

import io
import threading

import pymupdf
import pytest

from asr_backend import citation_import, full_text, models, upload_limits
from asr_backend.settings import settings

CSV_HEADER = "title,abstract,authors,year,source\n"


def _row(title: str) -> str:
    return f"{title},An abstract,Author,2020,PubMed\n"


def _ris(title: str) -> str:
    return f"TY  - JOUR\nTI  - {title}\nAU  - Doe, Jane\nPY  - 2019\nER  - \n"


def _create_project(client) -> str:
    return client.post(
        "/review-projects",
        json={"name": "My Review", "merge_mode": "combine", "review_mode": "solo"},
    ).json()["id"]


def _upload_citations(client, project_id: str, filename: str, content: str | bytes):
    return client.post(
        f"/review-projects/{project_id}/citations",
        files={"file": (filename, io.BytesIO(_as_bytes(content)), "text/plain")},
    )


def _as_bytes(content: str | bytes) -> bytes:
    return content.encode() if isinstance(content, str) else content


def _create_citation(client, project_id: str, title: str = "Study A") -> str:
    _upload_citations(client, project_id, "c.csv", CSV_HEADER + _row(title))
    listed = client.get(f"/review-projects/{project_id}/citations").json()
    return next(c["id"] for c in listed if c["title"] == title)


def _make_pdf(pages: int = 1) -> bytes:
    doc = pymupdf.open()
    for number in range(pages):
        doc.new_page().insert_text((72, 72), f"Page {number + 1} text")
    return doc.tobytes()


def _upload_pdf(client, project_id: str, citation_id: str, content: bytes, filename="paper.pdf"):
    return client.post(
        f"/review-projects/{project_id}/citations/{citation_id}/full-text",
        files={"file": (filename, io.BytesIO(content), "application/pdf")},
    )


def _citation_count(client, project_id: str) -> int:
    return len(client.get(f"/review-projects/{project_id}/citations").json())


def test_limits_match_the_agreed_product_numbers():
    assert upload_limits.MAX_CITATION_FILE_BYTES == 10 * 1024 * 1024
    assert upload_limits.MAX_CITATION_RECORDS == 20_000
    assert upload_limits.MAX_PDF_BYTES == 50 * 1024 * 1024
    assert upload_limits.MAX_PDF_PAGES == 200


# --- Citation files: size -----------------------------------------------------


def test_citation_file_over_the_size_limit_is_rejected_with_413(authed_client, monkeypatch):
    monkeypatch.setattr(upload_limits, "MAX_CITATION_FILE_BYTES", 500)
    project_id = _create_project(authed_client)

    response = _upload_citations(
        authed_client, project_id, "c.csv", CSV_HEADER + _row("A") + " " * 600
    )

    assert response.status_code == 413
    assert "limit" in response.json()["detail"]
    assert _citation_count(authed_client, project_id) == 0


def test_citation_file_exactly_at_the_size_limit_is_accepted(authed_client, monkeypatch):
    content = CSV_HEADER + _row("A")
    monkeypatch.setattr(upload_limits, "MAX_CITATION_FILE_BYTES", len(content))
    project_id = _create_project(authed_client)

    response = _upload_citations(authed_client, project_id, "c.csv", content)

    assert response.status_code == 201
    assert response.json()["created"] == 1


def test_a_413_carries_cors_headers_so_the_browser_can_show_the_message(
    authed_client, monkeypatch
):
    monkeypatch.setattr(upload_limits, "MAX_CITATION_FILE_BYTES", 100)
    monkeypatch.setattr(upload_limits, "MULTIPART_OVERHEAD_BYTES", 100)
    project_id = _create_project(authed_client)

    response = authed_client.post(
        f"/review-projects/{project_id}/citations",
        files={"file": ("c.csv", io.BytesIO(b"x" * 5000), "text/csv")},
        headers={"Origin": settings.frontend_origin},
    )

    assert response.status_code == 413
    assert response.headers["access-control-allow-origin"] == settings.frontend_origin


def test_a_chunked_upload_with_no_content_length_is_cut_off_at_the_limit(
    authed_client, monkeypatch
):
    monkeypatch.setattr(upload_limits, "MAX_CITATION_FILE_BYTES", 100)
    monkeypatch.setattr(upload_limits, "MULTIPART_OVERHEAD_BYTES", 100)
    project_id = _create_project(authed_client)
    boundary = "test-boundary"
    head = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="c.csv"\r\n'
        "Content-Type: text/csv\r\n\r\n"
    ).encode()
    tail = f"\r\n--{boundary}--\r\n".encode()

    def body():
        yield head
        for _ in range(100):
            yield b"x" * 1000
        yield tail

    response = authed_client.post(
        f"/review-projects/{project_id}/citations",
        content=body(),
        headers={"content-type": f"multipart/form-data; boundary={boundary}"},
    )

    assert response.status_code == 413
    assert _citation_count(authed_client, project_id) == 0


# --- Citation files: record count -----------------------------------------------


def test_csv_with_too_many_records_is_rejected_and_nothing_is_imported(
    authed_client, monkeypatch
):
    monkeypatch.setattr(upload_limits, "MAX_CITATION_RECORDS", 3)
    project_id = _create_project(authed_client)
    content = CSV_HEADER + "".join(_row(f"Study {n}") for n in range(4))

    response = _upload_citations(authed_client, project_id, "c.csv", content)

    assert response.status_code == 422
    assert "more than 3 records" in response.json()["detail"]
    assert _citation_count(authed_client, project_id) == 0


def test_csv_with_exactly_the_record_limit_is_accepted(authed_client, monkeypatch):
    monkeypatch.setattr(upload_limits, "MAX_CITATION_RECORDS", 3)
    project_id = _create_project(authed_client)
    content = CSV_HEADER + "".join(_row(f"Study {n}") for n in range(3))

    response = _upload_citations(authed_client, project_id, "c.csv", content)

    assert response.status_code == 201
    assert response.json()["created"] == 3


def test_ris_with_too_many_records_is_rejected_and_nothing_is_imported(
    authed_client, monkeypatch
):
    monkeypatch.setattr(upload_limits, "MAX_CITATION_RECORDS", 3)
    project_id = _create_project(authed_client)
    content = "".join(_ris(f"Study {n}") for n in range(4))

    response = _upload_citations(authed_client, project_id, "c.ris", content)

    assert response.status_code == 422
    assert "more than 3 records" in response.json()["detail"]
    assert _citation_count(authed_client, project_id) == 0


def test_rows_without_a_title_count_toward_the_record_limit(monkeypatch):
    monkeypatch.setattr(upload_limits, "MAX_CITATION_RECORDS", 3)
    content = CSV_HEADER + ",abstract only,,,\n" * 4

    with pytest.raises(citation_import.TooManyRecords):
        citation_import.parse_csv(content)


# --- Full-text PDFs -------------------------------------------------------------


def test_pdf_over_the_size_limit_is_rejected_with_413(authed_client, monkeypatch):
    project_id = _create_project(authed_client)
    citation_id = _create_citation(authed_client, project_id)
    pdf = _make_pdf()
    monkeypatch.setattr(upload_limits, "MAX_PDF_BYTES", len(pdf) - 1)
    monkeypatch.setattr(upload_limits, "MULTIPART_OVERHEAD_BYTES", len(pdf))

    response = _upload_pdf(authed_client, project_id, citation_id, pdf)

    assert response.status_code == 413
    assert "MB limit" in response.json()["detail"]
    detail = authed_client.get(f"/review-projects/{project_id}/citations/{citation_id}").json()
    assert detail["full_text"] is None


def test_pdf_over_the_limit_is_rejected_before_being_read_into_the_body(
    authed_client, monkeypatch
):
    project_id = _create_project(authed_client)
    citation_id = _create_citation(authed_client, project_id)
    pdf = _make_pdf()
    monkeypatch.setattr(upload_limits, "MAX_PDF_BYTES", len(pdf) - 1)
    monkeypatch.setattr(upload_limits, "MULTIPART_OVERHEAD_BYTES", 0)

    response = _upload_pdf(authed_client, project_id, citation_id, pdf)

    # The whole multipart body is over the limit, so the middleware answers,
    # not the handler.
    assert response.status_code == 413


def test_pdf_exactly_at_the_size_limit_is_accepted(authed_client, monkeypatch):
    project_id = _create_project(authed_client)
    citation_id = _create_citation(authed_client, project_id)
    pdf = _make_pdf()
    monkeypatch.setattr(upload_limits, "MAX_PDF_BYTES", len(pdf))

    response = _upload_pdf(authed_client, project_id, citation_id, pdf)

    assert response.status_code == 201


def test_pdf_over_the_page_limit_is_rejected_and_not_stored(authed_client, monkeypatch):
    monkeypatch.setattr(upload_limits, "MAX_PDF_PAGES", 2)
    project_id = _create_project(authed_client)
    citation_id = _create_citation(authed_client, project_id)

    response = _upload_pdf(authed_client, project_id, citation_id, _make_pdf(pages=3))

    assert response.status_code == 422
    assert "more than 2 pages" in response.json()["detail"]
    detail = authed_client.get(f"/review-projects/{project_id}/citations/{citation_id}").json()
    assert detail["full_text"] is None


def test_pdf_with_exactly_the_page_limit_is_accepted(authed_client, monkeypatch):
    monkeypatch.setattr(upload_limits, "MAX_PDF_PAGES", 2)
    project_id = _create_project(authed_client)
    citation_id = _create_citation(authed_client, project_id)

    response = _upload_pdf(authed_client, project_id, citation_id, _make_pdf(pages=2))

    assert response.status_code == 201


def test_a_file_named_pdf_without_the_pdf_header_is_rejected(authed_client):
    project_id = _create_project(authed_client)
    citation_id = _create_citation(authed_client, project_id)

    response = _upload_pdf(authed_client, project_id, citation_id, b"MZ not really a pdf")

    assert response.status_code == 422
    assert response.json()["detail"] == "File is not a valid PDF"
    detail = authed_client.get(f"/review-projects/{project_id}/citations/{citation_id}").json()
    assert detail["full_text"] is None


def test_a_pdf_with_stray_bytes_before_the_header_is_still_accepted(authed_client):
    project_id = _create_project(authed_client)
    citation_id = _create_citation(authed_client, project_id)

    response = _upload_pdf(authed_client, project_id, citation_id, b"\n\n" + _make_pdf())

    assert response.status_code == 201


def test_has_pdf_header_only_looks_at_the_start_of_the_file():
    assert full_text.has_pdf_header(b"%PDF-1.7\n...")
    assert not full_text.has_pdf_header(b"x" * 2000 + b"%PDF-1.7")


def test_full_text_cannot_be_uploaded_to_an_archived_citation(authed_client, db_session):
    project_id = _create_project(authed_client)
    _upload_citations(
        authed_client, project_id, "c.csv", CSV_HEADER + _row("Dup Study") + _row("Dup Study")
    )
    archived = db_session.query(models.Citation).filter_by(archived=True).one()

    response = _upload_pdf(authed_client, project_id, str(archived.id), _make_pdf())

    assert response.status_code == 409
    assert "merged into another" in response.json()["detail"]
    detail = authed_client.get(f"/review-projects/{project_id}/citations/{archived.id}").json()
    assert detail["full_text"] is None


# --- Parsing must not block the event loop -------------------------------------


def _assert_health_is_served_while_blocked_in(client, monkeypatch, module, attr, upload):
    """Runs `upload` with `module.attr` parked, and pings /health meanwhile.

    If the handler did its blocking work on the event loop, /health could not be
    answered until the park times out, and the timeout flag would be set.
    """
    started = threading.Event()
    release = threading.Event()
    timed_out = []
    real = getattr(module, attr)

    def parked(*args, **kwargs):
        started.set()
        if not release.wait(timeout=5):
            timed_out.append(True)
        return real(*args, **kwargs)

    monkeypatch.setattr(module, attr, parked)
    outcome = {}
    worker = threading.Thread(target=lambda: outcome.update(response=upload()))
    worker.start()
    try:
        assert started.wait(timeout=5), "the upload never reached the parse step"
        health = client.get("/health")
    finally:
        release.set()
        worker.join(timeout=10)

    assert not timed_out, "/health had to wait for the parse: the event loop was blocked"
    assert health.status_code == 200
    assert outcome["response"].status_code == 201


def test_another_request_is_served_while_a_citation_file_is_being_parsed(
    authed_client, monkeypatch
):
    project_id = _create_project(authed_client)

    _assert_health_is_served_while_blocked_in(
        authed_client,
        monkeypatch,
        citation_import,
        "parse_upload",
        lambda: _upload_citations(authed_client, project_id, "c.csv", CSV_HEADER + _row("A")),
    )


def test_another_request_is_served_while_a_pdf_is_being_parsed(authed_client, monkeypatch):
    project_id = _create_project(authed_client)
    citation_id = _create_citation(authed_client, project_id)

    _assert_health_is_served_while_blocked_in(
        authed_client,
        monkeypatch,
        full_text,
        "extract_text",
        lambda: _upload_pdf(authed_client, project_id, citation_id, _make_pdf()),
    )
