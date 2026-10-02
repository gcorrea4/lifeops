"""Router tests for /api/v1/blocks."""

from datetime import date


# ---------------------------------------------------------------------------
# POST /api/v1/blocks
# ---------------------------------------------------------------------------

def test_create_weekly_block(client):
    payload = {
        "title": "Faculdade",
        "recurrence_type": "weekly",
        "weekday": 0,
        "start_time": "08:00:00",
        "end_time": "10:00:00",
    }
    response = client.post("/api/v1/blocks/", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Faculdade"
    assert data["recurrence_type"] == "weekly"
    assert data["weekday"] == 0
    assert data["spans_next_day"] is False


def test_create_once_block(client):
    today = date.today().isoformat()
    payload = {
        "title": "Consulta médica",
        "recurrence_type": "once",
        "date": today,
        "start_time": "14:00:00",
        "end_time": "15:00:00",
    }
    response = client.post("/api/v1/blocks/", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["recurrence_type"] == "once"
    assert data["date"] == today
    assert data["weekday"] is None


def test_create_overnight_block(client):
    """A block that crosses midnight should have spans_next_day=True."""
    payload = {
        "title": "Plantão",
        "recurrence_type": "weekly",
        "weekday": 4,
        "start_time": "22:00:00",
        "end_time": "06:00:00",
    }
    response = client.post("/api/v1/blocks/", json=payload)
    assert response.status_code == 201
    assert response.json()["spans_next_day"] is True


def test_create_block_same_start_end_time(client):
    """start_time == end_time must be rejected by Pydantic (422)."""
    payload = {
        "title": "Inválido",
        "recurrence_type": "weekly",
        "weekday": 1,
        "start_time": "10:00:00",
        "end_time": "10:00:00",
    }
    response = client.post("/api/v1/blocks/", json=payload)
    assert response.status_code == 422


def test_create_weekly_block_without_weekday(client):
    """weekly without weekday must be rejected (422)."""
    payload = {
        "title": "Sem weekday",
        "recurrence_type": "weekly",
        "start_time": "09:00:00",
        "end_time": "10:00:00",
    }
    response = client.post("/api/v1/blocks/", json=payload)
    assert response.status_code == 422


def test_create_once_block_without_date(client):
    """once without date must be rejected (422)."""
    payload = {
        "title": "Sem data",
        "recurrence_type": "once",
        "start_time": "09:00:00",
        "end_time": "10:00:00",
    }
    response = client.post("/api/v1/blocks/", json=payload)
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/v1/blocks
# ---------------------------------------------------------------------------

def test_list_blocks(client):
    # Create one block first
    payload = {
        "title": "Trabalho",
        "recurrence_type": "weekly",
        "weekday": 2,
        "start_time": "09:00:00",
        "end_time": "17:00:00",
    }
    client.post("/api/v1/blocks/", json=payload)

    response = client.get("/api/v1/blocks/")
    assert response.status_code == 200
    blocks = response.json()
    assert isinstance(blocks, list)
    assert len(blocks) >= 1
    assert any(b["title"] == "Trabalho" for b in blocks)


def test_get_block_found(client):
    payload = {
        "title": "Aula de inglês",
        "recurrence_type": "weekly",
        "weekday": 3,
        "start_time": "18:00:00",
        "end_time": "20:00:00",
    }
    created = client.post("/api/v1/blocks/", json=payload).json()
    block_id = created["id"]

    response = client.get(f"/api/v1/blocks/{block_id}")
    assert response.status_code == 200
    assert response.json()["id"] == block_id


def test_get_block_not_found(client):
    response = client.get("/api/v1/blocks/99999")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/v1/blocks/{id}
# ---------------------------------------------------------------------------

def test_patch_block_title_only(client):
    """PATCH only title — spans_next_day should be recomputed from existing times."""
    payload = {
        "title": "Original",
        "recurrence_type": "weekly",
        "weekday": 0,
        "start_time": "08:00:00",
        "end_time": "10:00:00",
    }
    created = client.post("/api/v1/blocks/", json=payload).json()
    block_id = created["id"]

    response = client.patch(f"/api/v1/blocks/{block_id}", json={"title": "Atualizado"})
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Atualizado"
    # Non-overnight block — spans_next_day stays False after recomputation
    assert data["spans_next_day"] is False


def test_patch_block_makes_start_equal_end(client):
    """PATCH that results in start_time == end_time must be rejected (422)."""
    payload = {
        "title": "Bloco",
        "recurrence_type": "weekly",
        "weekday": 0,
        "start_time": "08:00:00",
        "end_time": "10:00:00",
    }
    created = client.post("/api/v1/blocks/", json=payload).json()
    block_id = created["id"]

    # Send end_time equal to the existing start_time
    response = client.patch(f"/api/v1/blocks/{block_id}", json={"end_time": "08:00:00"})
    assert response.status_code == 422


def test_patch_weekly_block_add_date_violates_mutex(client):
    """Adding a date to a weekly block violates mutual exclusivity → 422."""
    payload = {
        "title": "Weekly",
        "recurrence_type": "weekly",
        "weekday": 1,
        "start_time": "09:00:00",
        "end_time": "11:00:00",
    }
    created = client.post("/api/v1/blocks/", json=payload).json()
    block_id = created["id"]

    response = client.patch(
        f"/api/v1/blocks/{block_id}",
        json={"date": date.today().isoformat()},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# DELETE /api/v1/blocks/{id}
# ---------------------------------------------------------------------------

def test_delete_block(client):
    payload = {
        "title": "Para deletar",
        "recurrence_type": "weekly",
        "weekday": 0,
        "start_time": "07:00:00",
        "end_time": "08:00:00",
    }
    created = client.post("/api/v1/blocks/", json=payload).json()
    block_id = created["id"]

    response = client.delete(f"/api/v1/blocks/{block_id}")
    assert response.status_code == 204

    # Should be gone
    response = client.get(f"/api/v1/blocks/{block_id}")
    assert response.status_code == 404


def test_delete_block_not_found(client):
    response = client.delete("/api/v1/blocks/99999")
    assert response.status_code == 404
