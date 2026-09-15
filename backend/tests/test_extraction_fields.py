def create_project(authed_client, name: str = "My Review") -> str:
    response = authed_client.post("/review-projects", json={"name": name, "merge_mode": "combine"})
    return response.json()["id"]


def create_field(
    authed_client, project_id: str, name: str = "Sample size", description: str = "Number of participants"
) -> dict:
    response = authed_client.post(
        f"/review-projects/{project_id}/extraction-fields",
        json={"name": name, "description": description},
    )
    return response.json()


def test_create_extraction_field(authed_client):
    project_id = create_project(authed_client)

    response = authed_client.post(
        f"/review-projects/{project_id}/extraction-fields",
        json={"name": "Sample size", "description": "Number of participants"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Sample size"
    assert body["description"] == "Number of participants"
    assert body["archived"] is False
    assert "id" in body


def test_create_extraction_field_rejects_blank_name(authed_client):
    project_id = create_project(authed_client)

    response = authed_client.post(
        f"/review-projects/{project_id}/extraction-fields",
        json={"name": "   ", "description": "Number of participants"},
    )

    assert response.status_code == 422


def test_create_extraction_field_for_missing_review_project_returns_404(authed_client):
    response = authed_client.post(
        "/review-projects/00000000-0000-0000-0000-000000000000/extraction-fields",
        json={"name": "Sample size", "description": "Number of participants"},
    )

    assert response.status_code == 404


def test_list_extraction_fields(authed_client):
    project_id = create_project(authed_client)
    create_field(authed_client, project_id, name="Sample size")
    create_field(authed_client, project_id, name="Methodology")

    response = authed_client.get(f"/review-projects/{project_id}/extraction-fields")

    assert response.status_code == 200
    names = [field["name"] for field in response.json()]
    assert names == ["Sample size", "Methodology"]


def test_list_extraction_fields_is_scoped_to_review_project(authed_client):
    project_a = create_project(authed_client, "A")
    project_b = create_project(authed_client, "B")
    create_field(authed_client, project_a, name="Only in A")

    response = authed_client.get(f"/review-projects/{project_b}/extraction-fields")

    assert response.status_code == 200
    assert response.json() == []


def test_edit_extraction_field_name_and_description(authed_client):
    project_id = create_project(authed_client)
    field = create_field(authed_client, project_id)

    response = authed_client.put(
        f"/review-projects/{project_id}/extraction-fields/{field['id']}",
        json={"name": "Sample size (n)", "description": "Total enrolled participants"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Sample size (n)"
    assert body["description"] == "Total enrolled participants"


def test_edit_extraction_field_rejects_blank_name(authed_client):
    project_id = create_project(authed_client)
    field = create_field(authed_client, project_id)

    response = authed_client.put(
        f"/review-projects/{project_id}/extraction-fields/{field['id']}",
        json={"name": "   ", "description": "Total enrolled participants"},
    )

    assert response.status_code == 422


def test_edit_missing_extraction_field_returns_404(authed_client):
    project_id = create_project(authed_client)

    response = authed_client.put(
        f"/review-projects/{project_id}/extraction-fields/00000000-0000-0000-0000-000000000000",
        json={"name": "Sample size", "description": "Number of participants"},
    )

    assert response.status_code == 404


def test_archive_extraction_field_hides_it_from_the_active_list(authed_client):
    project_id = create_project(authed_client)
    field = create_field(authed_client, project_id, name="Sample size")
    create_field(authed_client, project_id, name="Methodology")

    response = authed_client.post(
        f"/review-projects/{project_id}/extraction-fields/{field['id']}/archive"
    )

    assert response.status_code == 200
    assert response.json()["archived"] is True

    active = authed_client.get(f"/review-projects/{project_id}/extraction-fields").json()
    names = [f["name"] for f in active]
    assert names == ["Methodology"]


def test_archiving_a_field_preserves_its_name_and_description(authed_client):
    project_id = create_project(authed_client)
    field = create_field(authed_client, project_id, name="Sample size", description="n participants")

    authed_client.post(f"/review-projects/{project_id}/extraction-fields/{field['id']}/archive")
    edited = authed_client.put(
        f"/review-projects/{project_id}/extraction-fields/{field['id']}",
        json={"name": "Sample size", "description": "n participants"},
    )

    # An archived field's row (and any values recorded against it) still exists
    # and can still be read back — archiving only hides it from the active list.
    assert edited.status_code == 200
    assert edited.json()["name"] == "Sample size"
    assert edited.json()["description"] == "n participants"
    assert edited.json()["archived"] is True


def test_archiving_an_already_archived_field_is_idempotent(authed_client):
    project_id = create_project(authed_client)
    field = create_field(authed_client, project_id)

    authed_client.post(f"/review-projects/{project_id}/extraction-fields/{field['id']}/archive")
    response = authed_client.post(
        f"/review-projects/{project_id}/extraction-fields/{field['id']}/archive"
    )

    assert response.status_code == 200
    assert response.json()["archived"] is True


def test_archive_missing_extraction_field_returns_404(authed_client):
    project_id = create_project(authed_client)

    response = authed_client.post(
        f"/review-projects/{project_id}/extraction-fields/"
        "00000000-0000-0000-0000-000000000000/archive"
    )

    assert response.status_code == 404
