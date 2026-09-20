import threading

import pytest


def create_project(authed_client, name: str = "My Review") -> str:
    response = authed_client.post(
        "/review-projects",
        json={"name": name, "merge_mode": "combine", "review_mode": "solo"},
    )
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


# --- Active names are unique within a Review Project (#67) ---------------------------------


def _extraction_fields_url(project_id: str) -> str:
    return f"/review-projects/{project_id}/extraction-fields"


def _field_url(project_id: str, field_id: str) -> str:
    return f"{_extraction_fields_url(project_id)}/{field_id}"


def _rename(authed_client, project_id: str, field: dict, name: str, description="d"):
    return authed_client.put(
        _field_url(project_id, field["id"]), json={"name": name, "description": description}
    )


def _active_names(authed_client, project_id: str) -> list[str]:
    return [f["name"] for f in authed_client.get(_extraction_fields_url(project_id)).json()]


def test_creating_a_second_field_with_the_same_name_is_a_409(authed_client):
    project_id = create_project(authed_client)
    create_field(authed_client, project_id, "Sample size")

    response = authed_client.post(
        _extraction_fields_url(project_id), json={"name": "Sample size", "description": None}
    )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        'An active Extraction Field named "Sample size" already exists in this Review Project'
    )
    assert _active_names(authed_client, project_id) == ["Sample size"]


@pytest.mark.parametrize("name", ["sample size", "SAMPLE SIZE", "Sample Size"])
def test_a_name_that_differs_only_in_case_is_a_duplicate(authed_client, name):
    project_id = create_project(authed_client)
    create_field(authed_client, project_id, "Sample size")

    response = authed_client.post(
        _extraction_fields_url(project_id), json={"name": name, "description": None}
    )

    assert response.status_code == 409


def test_a_name_that_differs_only_in_surrounding_whitespace_is_a_duplicate(authed_client):
    project_id = create_project(authed_client)
    create_field(authed_client, project_id, "Sample size")

    response = authed_client.post(
        _extraction_fields_url(project_id), json={"name": "  Sample size\t", "description": None}
    )

    assert response.status_code == 409


def test_inner_whitespace_still_makes_a_name_different(authed_client):
    project_id = create_project(authed_client)
    create_field(authed_client, project_id, "Sample size")

    response = authed_client.post(
        _extraction_fields_url(project_id), json={"name": "Sample  size", "description": None}
    )

    assert response.status_code == 201


def test_the_same_name_is_fine_in_another_review_project(authed_client):
    first = create_project(authed_client, "First")
    second = create_project(authed_client, "Second")
    create_field(authed_client, first, "Sample size")

    response = authed_client.post(
        _extraction_fields_url(second), json={"name": "Sample size", "description": None}
    )

    assert response.status_code == 201


def test_an_archived_field_does_not_block_reusing_its_name(authed_client):
    project_id = create_project(authed_client)
    old = create_field(authed_client, project_id, "Sample size")
    authed_client.post(f"{_field_url(project_id, old['id'])}/archive")

    response = authed_client.post(
        _extraction_fields_url(project_id), json={"name": "sample size", "description": None}
    )

    assert response.status_code == 201
    assert _active_names(authed_client, project_id) == ["sample size"]


def test_several_archived_fields_may_share_a_name(authed_client):
    project_id = create_project(authed_client)
    for _ in range(2):
        field = create_field(authed_client, project_id, "Sample size")
        authed_client.post(f"{_field_url(project_id, field['id'])}/archive")

    assert create_field(authed_client, project_id, "Sample size")["archived"] is False


def test_renaming_a_field_to_another_active_fields_name_is_a_409(authed_client):
    project_id = create_project(authed_client)
    create_field(authed_client, project_id, "Sample size")
    other = create_field(authed_client, project_id, "Follow-up")

    response = _rename(authed_client, project_id, other, "SAMPLE SIZE")

    assert response.status_code == 409
    assert "SAMPLE SIZE" in response.json()["detail"]
    assert sorted(_active_names(authed_client, project_id)) == ["Follow-up", "Sample size"]


def test_a_field_can_be_saved_under_its_own_name_to_change_only_the_description(authed_client):
    project_id = create_project(authed_client)
    field = create_field(authed_client, project_id, "Sample size")

    response = _rename(authed_client, project_id, field, "Sample size", "New description")

    assert response.status_code == 200
    assert response.json()["description"] == "New description"


def test_a_field_can_change_only_the_case_of_its_own_name(authed_client):
    project_id = create_project(authed_client)
    field = create_field(authed_client, project_id, "sample size")

    response = _rename(authed_client, project_id, field, "Sample Size")

    assert response.status_code == 200
    assert response.json()["name"] == "Sample Size"


def test_a_field_can_be_renamed_to_the_name_of_an_archived_field(authed_client):
    project_id = create_project(authed_client)
    old = create_field(authed_client, project_id, "Sample size")
    authed_client.post(f"{_field_url(project_id, old['id'])}/archive")
    other = create_field(authed_client, project_id, "Follow-up")

    response = _rename(authed_client, project_id, other, "Sample size")

    assert response.status_code == 200


def test_an_archived_field_can_be_renamed_to_an_active_fields_name(authed_client):
    project_id = create_project(authed_client)
    old = create_field(authed_client, project_id, "Old name")
    authed_client.post(f"{_field_url(project_id, old['id'])}/archive")
    create_field(authed_client, project_id, "Sample size")

    response = _rename(authed_client, project_id, old, "Sample size")

    assert response.status_code == 200


def test_two_simultaneous_creates_of_the_same_name_leave_exactly_one(authed_client):
    project_id = create_project(authed_client)
    barrier = threading.Barrier(2)
    statuses = []

    def create():
        barrier.wait()
        statuses.append(
            authed_client.post(
                _extraction_fields_url(project_id), json={"name": "Sample size"}
            ).status_code
        )

    threads = [threading.Thread(target=create) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert sorted(statuses) == [201, 409]
    assert _active_names(authed_client, project_id) == ["Sample size"]
