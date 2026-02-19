import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "rag"))
import server

server.app.config["TESTING"] = True


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "BASE_PATH", str(tmp_path))
    server._clients.clear()
    server._collections.clear()
    with server.app.test_client() as c:
        yield c


def test_project_isolation(client):
    client.post("/index", json={
        "project": "alpha",
        "documents": ["def login(): pass"],
        "ids": ["alpha::auth.py::0"],
        "metadatas": [{"type": "code", "file": "auth.py"}]
    })
    client.post("/index", json={
        "project": "beta",
        "documents": ["def checkout(): pass"],
        "ids": ["beta::shop.py::0"],
        "metadatas": [{"type": "code", "file": "shop.py"}]
    })
    r = client.post("/search", json={"project": "alpha", "query": "login", "n_results": 5})
    assert r.status_code == 200
    data = r.get_json()
    assert "results" in data
    assert data.get("project") == "alpha"
    docs = data["results"]["documents"][0]
    assert any("login" in d for d in docs)
    assert not any("checkout" in d for d in docs)


def test_upsert_is_idempotent(client):
    for _ in range(3):
        r = client.post("/index", json={
            "project": "idem",
            "documents": ["def foo(): pass"],
            "ids": ["idem::foo.py::0"],
            "metadatas": [{"type": "code"}]
        })
        assert r.status_code == 200
    # After 3 upserts of same ID there should only be 1 document
    r = client.post("/search", json={"project": "idem", "query": "foo", "n_results": 10})
    assert r.status_code == 200
    docs = r.get_json()["results"]["documents"][0]
    assert len(docs) == 1


def test_stats_endpoint_does_not_error(client):
    # Stats for default project — just verify no 500 error
    r = client.get("/stats")
    assert r.status_code == 200


def test_health_endpoint(client):
    r = client.get("/health")
    assert r.status_code == 200
    data = r.get_json()
    assert data["status"] == "healthy"


def test_index_returns_project_in_response(client):
    r = client.post("/index", json={
        "project": "myproj",
        "documents": ["def bar(): pass"],
        "ids": ["myproj::bar.py::0"],
        "metadatas": [{"type": "code"}]
    })
    assert r.status_code == 200
    data = r.get_json()
    assert data["indexed"] == 1
    assert data["project"] == "myproj"


def test_search_requires_query(client):
    r = client.post("/search", json={"project": "alpha"})
    assert r.status_code == 400
    assert "error" in r.get_json()


def test_index_requires_documents(client):
    r = client.post("/index", json={"project": "alpha", "documents": []})
    assert r.status_code == 400
    assert "error" in r.get_json()


def test_list_projects(client):
    client.post("/index", json={"project": "proj-a", "documents": ["x"], "ids": ["proj-a::f::0"], "metadatas": [{"type": "code"}]})
    r = client.get("/projects")
    assert r.status_code == 200
    names = [p["name"] for p in r.get_json()["projects"]]
    assert "proj-a" in names


def test_delete_project(client):
    client.post("/index", json={"project": "to-delete", "documents": ["x"], "ids": ["to-delete::f::0"], "metadatas": [{"type": "code"}]})
    r = client.delete("/projects/to-delete")
    assert r.status_code == 200
    r2 = client.get("/projects")
    names = [p["name"] for p in r2.get_json()["projects"]]
    assert "to-delete" not in names


def test_init_project(client):
    r = client.post("/projects/newproj/init")
    assert r.status_code == 200
    assert r.get_json()["initialized"] == "newproj"


def test_project_stats(client):
    client.post("/index", json={"project": "stat-proj", "documents": ["hello"], "ids": ["stat-proj::h::0"], "metadatas": [{"type": "code"}]})
    r = client.get("/projects/stat-proj/stats")
    assert r.status_code == 200
    data = r.get_json()
    assert data["name"] == "stat-proj"
    assert data["count"] == 1


def test_ui_endpoint(client):
    r = client.get("/ui")
    assert r.status_code == 200
    html = r.data.decode()
    assert "<form" in html
    assert "<table" in html
    assert "project" in html


def test_search_filter_by_type(client):
    client.post("/index", json={
        "project": "filter-test",
        "documents": ["def login(): pass", "## BUG-001 Auth ticket content"],
        "ids": ["filter-test::auth.py::0", "filter-test::BUG-001.md::0"],
        "metadatas": [{"type": "code"}, {"type": "ticket"}]
    })
    r = client.post("/search", json={
        "project": "filter-test",
        "query": "login",
        "n_results": 5,
        "filter": {"type": "code"}
    })
    assert r.status_code == 200
    docs = r.get_json()["results"]["documents"][0]
    # Should return code doc, not the ticket
    assert len(docs) >= 1
    assert all("def login" in d or "pass" in d for d in docs)
