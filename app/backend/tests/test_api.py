import pytest

import app as app_module


def test_frontend_is_served_by_api(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.mimetype == "text/html"
    assert b'/assets/app.js' in response.data
    assert b'http://localhost:5000' not in response.data
    asset = client.get("/assets/app.js")
    assert asset.status_code == 200
    assert b'const API_BASE = window.API_BASE_URL || "";' in asset.data
    assert client.get("/api/tasks").status_code == 200


def test_static_files_do_not_expose_backend(client):
    assert client.get("/assets/../backend/app.py").status_code == 404
    assert client.get("/assets/tasks.json").status_code == 404
    assert client.get("/api/not-found").status_code == 404


def test_list_tasks_returns_seed_data(client):
    res = client.get("/api/tasks")
    assert res.status_code == 200
    assert set(res.json) == {"items", "page", "page_size", "total", "total_pages"}
    assert [t["id"] for t in res.json["items"]] == list(range(1, 11))
    assert {k: v for k, v in res.json.items() if k != "items"} == {
        "page": 1, "page_size": 10, "total": 15, "total_pages": 2,
    }


@pytest.mark.parametrize("query, ids, page, size, pages", [
    ("page=2", list(range(11, 16)), 2, 10, 2),
    ("page_size=4&page=2", [5, 6, 7, 8], 2, 4, 4),
    ("page_size=1", [1], 1, 1, 15),
    ("page_size=50", list(range(1, 16)), 1, 50, 1),
    ("page_size=5&page=3", list(range(11, 16)), 3, 5, 3),
    ("page=99", [], 99, 10, 2),
])
def test_list_tasks_pagination(client, query, ids, page, size, pages):
    res = client.get(f"/api/tasks?{query}")
    assert res.status_code == 200
    assert [t["id"] for t in res.json["items"]] == ids
    assert res.json["page"] == page
    assert res.json["page_size"] == size
    assert res.json["total"] == 15
    assert res.json["total_pages"] == pages


@pytest.mark.parametrize("name", ["page", "page_size"])
@pytest.mark.parametrize("value", ["", "abc", "1.5", "1e1", "true", "1_0", "NaN"])
def test_list_tasks_rejects_non_integer_parameters(client, name, value):
    res = client.get("/api/tasks", query_string={name: value})
    assert res.status_code == 400
    assert res.is_json
    assert name in res.json["error"]


@pytest.mark.parametrize("query, name", [
    ("page=0", "page"), ("page=-1", "page"),
    ("page_size=0", "page_size"), ("page_size=-1", "page_size"),
    ("page_size=51", "page_size"),
])
def test_list_tasks_rejects_out_of_range_parameters(client, query, name):
    res = client.get(f"/api/tasks?{query}")
    assert res.status_code == 400
    assert res.is_json
    assert name in res.json["error"]


def test_list_tasks_empty(client):
    app_module.tasks.clear()
    res = client.get("/api/tasks")
    assert res.status_code == 200
    assert res.json == {
        "items": [], "page": 1, "page_size": 10, "total": 0, "total_pages": 0,
    }


def test_list_tasks_sorts_before_paginating(client):
    app_module.tasks = dict(reversed(list(app_module.tasks.items())))
    res = client.get("/api/tasks?page=2&page_size=4")
    assert [t["id"] for t in res.json["items"]] == [5, 6, 7, 8]


def test_list_tasks_reflects_mutations(client, valid_task):
    assert client.post("/api/tasks", json=valid_task).status_code == 201
    res = client.get("/api/tasks?page=2")
    assert res.json["total"] == 16
    assert [t["id"] for t in res.json["items"]] == list(range(11, 17))
    assert client.delete("/api/tasks/11").status_code == 204
    res = client.get("/api/tasks?page=2")
    assert res.json["total"] == 15
    assert [t["id"] for t in res.json["items"]] == list(range(12, 17))


def test_get_task_by_id(client):
    res = client.get("/api/tasks/1")
    assert res.status_code == 200
    assert res.json["assignedTo"] == "Mohan"


def test_get_missing_task_returns_404(client):
    assert client.get("/api/tasks/999").status_code == 404


def test_meta_returns_dropdown_values(client):
    res = client.get("/api/meta")
    assert res.status_code == 200
    assert "Hema" in res.json["assignees"]
    assert "Deployment" in res.json["areas"]
    assert res.json["priorities"] == [1, 2, 3, 4]


def test_create_task(client, valid_task):
    res = client.post("/api/tasks", json=valid_task)
    assert res.status_code == 201
    assert res.json["id"] == 16
    assert client.get("/api/tasks/16").json["title"] == valid_task["title"]


def test_create_task_without_title_returns_400(client, valid_task):
    valid_task["title"] = "   "
    assert client.post("/api/tasks", json=valid_task).status_code == 400


def test_create_task_with_invalid_priority_returns_400(client, valid_task):
    valid_task["priority"] = 5
    assert client.post("/api/tasks", json=valid_task).status_code == 400


def test_create_task_with_unknown_assignee_returns_400(client, valid_task):
    valid_task["assignedTo"] = "John"
    assert client.post("/api/tasks", json=valid_task).status_code == 400


def test_create_task_with_end_before_start_returns_400(client, valid_task):
    valid_task["endDate"] = "2026-10-01"
    assert client.post("/api/tasks", json=valid_task).status_code == 400


def test_create_same_day_task_is_allowed(client, valid_task):
    valid_task["endDate"] = valid_task["startDate"]
    res = client.post("/api/tasks", json=valid_task)
    assert res.status_code == 201, res.json


def test_update_task(client, valid_task):
    res = client.put("/api/tasks/3", json=valid_task)
    assert res.status_code == 200
    assert res.json["id"] == 3
    assert client.get("/api/tasks/3").json["title"] == valid_task["title"]


def test_update_same_day_task_is_allowed(client, valid_task):
    valid_task["endDate"] = valid_task["startDate"]
    res = client.put("/api/tasks/3", json=valid_task)
    assert res.status_code == 200, res.json
    task = client.get("/api/tasks/3").json
    assert task["endDate"] == task["startDate"] == valid_task["startDate"]


def test_update_task_with_end_before_start_returns_400(client, valid_task):
    original = client.get("/api/tasks/3").json
    valid_task["endDate"] = "2026-10-01"
    res = client.put("/api/tasks/3", json=valid_task)
    assert res.status_code == 400
    assert res.json == {"error": "endDate cannot be before startDate"}
    assert client.get("/api/tasks/3").json == original


def test_update_missing_task_returns_404(client, valid_task):
    res = client.put("/api/tasks/999", json=valid_task)
    assert res.status_code == 404


def test_delete_task(client):
    assert client.delete("/api/tasks/2").status_code == 204
    assert client.get("/api/tasks/2").status_code == 404


def test_delete_missing_task_returns_404(client):
    assert client.delete("/api/tasks/999").status_code == 404


def test_openapi_spec_is_served(client):
    res = client.get("/openapi.json")
    assert res.status_code == 200
    assert "/api/tasks" in res.json["paths"]
    operation = res.json["paths"]["/api/tasks"]["get"]
    parameters = {p["name"]: p["schema"] for p in operation["parameters"]}
    assert parameters == {
        "page": {"type": "integer", "minimum": 1, "default": 1},
        "page_size": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
    }
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/TaskPage",
    }
    assert "application/json" in operation["responses"]["400"]["content"]
    schema = res.json["components"]["schemas"]["TaskPage"]
    assert set(schema["required"]) == {"items", "page", "page_size", "total", "total_pages"}
    assert schema["properties"]["total_pages"]["minimum"] == 0
