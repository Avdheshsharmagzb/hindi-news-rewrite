"""Backend API tests for Hindi Editorial Newsroom CMS."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://hindi-news-rewrite.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

STATUS_PENDING = "Pending_Review"
STATUS_REWRITTEN = "Rewritten_Pending_Publish"
STATUS_PUBLISHED = "Published"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ---- Stats ----
def test_stats_shape_and_seed(session):
    r = session.get(f"{API}/stats", timeout=15)
    assert r.status_code == 200
    data = r.json()
    for k in ("total", "pending", "rewritten", "published"):
        assert k in data
        assert isinstance(data[k], int)
    # Seed expectation (allowed to grow because prior tests created items)
    assert data["total"] >= 7
    assert data["pending"] >= 1
    assert data["published"] >= 1


# ---- List / filter ----
def test_list_news_all(session):
    r = session.get(f"{API}/news", timeout=15)
    assert r.status_code == 200
    items = r.json()
    assert isinstance(items, list)
    assert len(items) >= 7
    # Ensure no mongo _id leaks
    assert all("_id" not in it for it in items)


@pytest.mark.parametrize("status", [STATUS_PENDING, STATUS_REWRITTEN, STATUS_PUBLISHED])
def test_list_news_filter_status(session, status):
    r = session.get(f"{API}/news", params={"status": status}, timeout=15)
    assert r.status_code == 200
    items = r.json()
    assert all(it["status"] == status for it in items)


# ---- Create ----
def test_create_news_defaults_pending(session):
    payload = {
        "headline": "TEST_ Sample headline for automated test",
        "content": "TEST_ This is sample body content used strictly for automated verification.",
        "category": "National",
        "source": "TEST",
        "source_language": "en",
    }
    r = session.post(f"{API}/news", json=payload, timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert data["headline"] == payload["headline"]
    assert data["status"] == STATUS_PENDING
    assert "id" in data
    # verify persistence
    r2 = session.get(f"{API}/news", params={"status": STATUS_PENDING}, timeout=15)
    assert any(it["id"] == data["id"] for it in r2.json())
    # cleanup
    session.delete(f"{API}/news/{data['id']}", timeout=15)


# ---- Publish invalid state ----
def test_publish_pending_returns_400(session):
    payload = {"headline": "TEST_ publish invalid", "content": "TEST_ body for invalid publish test."}
    r = session.post(f"{API}/news", json=payload, timeout=15)
    assert r.status_code == 200
    item_id = r.json()["id"]
    try:
        r2 = session.post(f"{API}/news/{item_id}/publish", timeout=15)
        assert r2.status_code == 400
    finally:
        session.delete(f"{API}/news/{item_id}", timeout=15)


# ---- Delete + 404 ----
def test_delete_and_404(session):
    r = session.post(f"{API}/news", json={"headline": "TEST_ del", "content": "TEST_ body"}, timeout=15)
    item_id = r.json()["id"]
    d = session.delete(f"{API}/news/{item_id}", timeout=15)
    assert d.status_code == 200
    assert d.json().get("deleted") is True
    d2 = session.delete(f"{API}/news/{item_id}", timeout=15)
    assert d2.status_code == 404


# ---- Full rewrite -> publish flow (AI call, slow) ----
def test_rewrite_and_publish_flow(session):
    payload = {
        "headline": "TEST_ Government launches new initiative for renewable energy",
        "content": (
            "TEST_ The government today announced a new initiative to boost renewable energy across the country. "
            "Officials said the plan targets 500 gigawatts of capacity by 2030 and will create over one lakh jobs. "
            "The initiative includes subsidies for solar rooftops and incentives for green hydrogen production."
        ),
        "category": "National",
        "source": "TEST",
        "source_language": "en",
    }
    created = session.post(f"{API}/news", json=payload, timeout=15).json()
    item_id = created["id"]

    stats_before = session.get(f"{API}/stats", timeout=15).json()

    try:
        r = session.post(f"{API}/news/{item_id}/rewrite", timeout=120)
        assert r.status_code == 200, f"Rewrite failed: {r.status_code} {r.text}"
        data = r.json()
        assert data["status"] == STATUS_REWRITTEN
        assert data["headline"] == payload["headline"], "Original headline must remain intact"
        assert data["content"] == payload["content"], "Original content must remain intact"
        assert data["rewritten_headline"] and len(data["rewritten_headline"]) > 0
        assert data["rewritten_content"] and len(data["rewritten_content"]) > 0
        # Devanagari check
        assert any("\u0900" <= ch <= "\u097F" for ch in data["rewritten_headline"]), "rewritten_headline must be Devanagari"
        assert any("\u0900" <= ch <= "\u097F" for ch in data["rewritten_content"]), "rewritten_content must be Devanagari"

        # Stats: pending should decrease by 1, rewritten increase by 1
        stats_after = session.get(f"{API}/stats", timeout=15).json()
        assert stats_after["pending"] == stats_before["pending"] - 1
        assert stats_after["rewritten"] == stats_before["rewritten"] + 1

        # Publish
        p = session.post(f"{API}/news/{item_id}/publish", timeout=15)
        assert p.status_code == 200
        assert p.json()["status"] == STATUS_PUBLISHED
    finally:
        session.delete(f"{API}/news/{item_id}", timeout=15)


def test_rewrite_nonexistent_returns_404(session):
    r = session.post(f"{API}/news/does-not-exist-xyz/rewrite", timeout=30)
    assert r.status_code == 404
