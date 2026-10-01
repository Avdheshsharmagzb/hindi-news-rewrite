"""Tests for the new news fetch + cron endpoints."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"
CRON_SECRET = "9f3c7a1e8b4d26f05c9a1be73d84f6029a7c15e2b8c0d1a6"

STATUS_PENDING = "Pending_Review"
EXPECTED_CATS = {
    "राष्ट्रीय", "दिल्ली", "गाज़ियाबाद", "नोएडा", "ग्रेटर नोएडा",
    "हापुड़", "मेरठ", "मुज़फ़्फ़रनगर", "लखनऊ प्रशासनिक तबादले",
}


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def test_fetch_news_returns_shape(session):
    r = session.post(f"{API}/news/fetch", timeout=60)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "fetched" in data
    assert "by_category" in data
    assert isinstance(data["fetched"], int)
    assert isinstance(data["by_category"], dict)


def test_fetch_news_dedup_on_second_call(session):
    # Run once (may be 0 if already fetched recently)
    session.post(f"{API}/news/fetch", timeout=60)
    # Immediate second call should yield 0 new items (dedup)
    r = session.post(f"{API}/news/fetch", timeout=60)
    assert r.status_code == 200
    data = r.json()
    assert data["fetched"] == 0, f"Expected dedup, got {data}"


def test_fetched_items_have_expected_fields(session):
    # Query Pending_Review items and verify fetched items have source_url + locality category
    r = session.get(f"{API}/news", params={"status": STATUS_PENDING}, timeout=20)
    assert r.status_code == 200
    items = r.json()
    # Any item with source_url should have a non-empty category
    fetched_items = [it for it in items if it.get("source_url")]
    if not fetched_items:
        pytest.skip("No fetched items currently in DB (feeds may be empty <=4h)")
    for it in fetched_items:
        assert it["status"] == STATUS_PENDING
        assert it["category"]
        assert it["source_url"].startswith("http")
    # At least one category should be from our expected locality set
    cats = {it["category"] for it in fetched_items}
    assert cats & EXPECTED_CATS, f"No expected categories: {cats}"


# ---- Cron auth ----
def test_cron_missing_auth_401(session):
    r = requests.post(f"{API}/cron/fetch-news", timeout=15)
    assert r.status_code == 401


def test_cron_wrong_token_401():
    r = requests.post(
        f"{API}/cron/fetch-news",
        headers={"Authorization": "Bearer wrong-token-xyz"},
        timeout=15,
    )
    assert r.status_code == 401


def test_cron_correct_token_200():
    r = requests.post(
        f"{API}/cron/fetch-news",
        headers={"Authorization": f"Bearer {CRON_SECRET}"},
        timeout=15,
    )
    assert r.status_code == 200
    assert r.json().get("accepted") is True
