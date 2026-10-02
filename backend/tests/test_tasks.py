"""Router tests for /api/v1/tasks."""

from datetime import date, timedelta


# ---------------------------------------------------------------------------
# POST /api/v1/tasks
# ---------------------------------------------------------------------------

def test_create_task(client):
    payload = {
        "title": "Estudar SQLAlchemy",
        "duration_minutes": 90,
    }
    response = client.post("/api/v1/tasks/", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Estudar SQLAlchemy"
    assert data["duration_minutes"] == 90
    assert data["status"] == "pending"
    assert data["priority"] == "medium"  # default


def test_create_task_zero_duration(client):
    payload = {"title": "Inválida", "duration_minutes": 0}
    response = client.post("/api/v1/tasks/", json=payload)
    assert response.status_code == 422


def test_create_task_negative_duration(client):
    payload = {"title": "Inválida", "duration_minutes": -10}
    response = client.post("/api/v1/tasks/", json=payload)
    assert response.status_code == 422


def test_create_task_past_deadline(client):
    past = (date.today() - timedelta(days=1)).isoformat()
    payload = {
        "title": "Prazo passado",
        "duration_minutes": 60,
        "deadline": past,
    }
    response = client.post("/api/v1/tasks/", json=payload)
    assert response.status_code == 422


def test_create_task_future_deadline(client):
    future = (date.today() + timedelta(days=7)).isoformat()
    payload = {
        "title": "Com prazo",
        "duration_minutes": 60,
        "deadline": future,
    }
    response = client.post("/api/v1/tasks/", json=payload)
    assert response.status_code == 201
    assert response.json()["deadline"] == future


# ---------------------------------------------------------------------------
# GET /api/v1/tasks
# ---------------------------------------------------------------------------

def test_list_tasks(client):
    client.post("/api/v1/tasks/", json={"title": "T1", "duration_minutes": 30})
    client.post("/api/v1/tasks/", json={"title": "T2", "duration_minutes": 45})

    response = client.get("/api/v1/tasks/")
    assert response.status_code == 200
    tasks = response.json()
    assert isinstance(tasks, list)
    assert len(tasks) >= 2


def test_list_tasks_filter_by_status(client):
    client.post("/api/v1/tasks/", json={"title": "Filtrada", "duration_minutes": 60})

    response = client.get("/api/v1/tasks/?status=pending")
    assert response.status_code == 200
    tasks = response.json()
    assert all(t["status"] == "pending" for t in tasks)

    response = client.get("/api/v1/tasks/?status=scheduled")
    assert response.status_code == 200
    assert response.json() == []


def test_list_tasks_invalid_status(client):
    response = client.get("/api/v1/tasks/?status=invalid_value")
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/v1/tasks/{id}
# ---------------------------------------------------------------------------

def test_get_task_found(client):
    created = client.post(
        "/api/v1/tasks/", json={"title": "Buscar", "duration_minutes": 20}
    ).json()
    task_id = created["id"]

    response = client.get(f"/api/v1/tasks/{task_id}")
    assert response.status_code == 200
    assert response.json()["id"] == task_id


def test_get_task_not_found(client):
    response = client.get("/api/v1/tasks/99999")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/v1/tasks/{id}
# ---------------------------------------------------------------------------

def test_patch_task_title_and_duration(client):
    created = client.post(
        "/api/v1/tasks/", json={"title": "Original", "duration_minutes": 30}
    ).json()
    task_id = created["id"]

    response = client.patch(
        f"/api/v1/tasks/{task_id}",
        json={"title": "Novo título", "duration_minutes": 60},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Novo título"
    assert data["duration_minutes"] == 60
    assert data["status"] == "pending"  # status unchanged


def test_patch_task_past_deadline_rejected(client):
    """PATCH sending a past deadline must be rejected (422)."""
    created = client.post(
        "/api/v1/tasks/", json={"title": "Prazo", "duration_minutes": 30}
    ).json()
    task_id = created["id"]

    past = (date.today() - timedelta(days=1)).isoformat()
    response = client.patch(f"/api/v1/tasks/{task_id}", json={"deadline": past})
    assert response.status_code == 422


def test_patch_task_without_deadline_field_is_valid_even_if_stored_deadline_passed(
    client, db_session
):
    """PATCH that omits deadline must succeed even if the stored deadline is past.

    We set the deadline directly in the DB to simulate an overdue task.
    """
    from app.models.task import Task

    created = client.post(
        "/api/v1/tasks/", json={"title": "Overdue", "duration_minutes": 30}
    ).json()
    task_id = created["id"]

    # Manually set a past deadline directly in the DB (bypassing schema validation)
    past = date.today() - timedelta(days=10)
    db_task = db_session.query(Task).filter(Task.id == task_id).first()
    db_task.deadline = past
    db_session.commit()

    # PATCH without deadline field — must succeed
    response = client.patch(
        f"/api/v1/tasks/{task_id}", json={"title": "Still valid"}
    )
    assert response.status_code == 200
    assert response.json()["title"] == "Still valid"


def test_patch_task_invalid_duration(client):
    created = client.post(
        "/api/v1/tasks/", json={"title": "T", "duration_minutes": 30}
    ).json()
    task_id = created["id"]

    response = client.patch(f"/api/v1/tasks/{task_id}", json={"duration_minutes": -1})
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# DELETE /api/v1/tasks/{id}
# ---------------------------------------------------------------------------

def test_delete_task(client):
    created = client.post(
        "/api/v1/tasks/", json={"title": "Para deletar", "duration_minutes": 15}
    ).json()
    task_id = created["id"]

    response = client.delete(f"/api/v1/tasks/{task_id}")
    assert response.status_code == 204

    response = client.get(f"/api/v1/tasks/{task_id}")
    assert response.status_code == 404


def test_delete_task_not_found(client):
    response = client.delete("/api/v1/tasks/99999")
    assert response.status_code == 404
