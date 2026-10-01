"""Backend tests for image-generation + publisher-brand feature.

Cost control: only ONE real image generation is triggered.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL", "https://hindi-news-rewrite.preview.emergentagent.com"
).rstrip("/")
API = f"{BASE_URL}/api"

BRAND = "गाजियाबाद टाइम्स"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ---------- helpers ----------
def _list(session, status=None):
    r = session.get(f"{API}/news", params={"status": status} if status else None, timeout=20)
    assert r.status_code == 200
    return r.json()


# ---------- Data model: brand + source hidden policy ----------
def test_rewritten_items_expose_publisher_brand_and_image_fields(session):
    items = _list(session, "Rewritten_Pending_Publish")
    assert items, "Need at least one rewritten item for test"
    for it in items:
        assert it.get("publisher_brand") == BRAND
        assert "image_url" in it
        assert "image_status" in it
        # original source must still be present in DB/API (hidden only in UI)
        assert "source" in it


def test_published_items_have_publisher_brand(session):
    items = _list(session, "Published")
    assert items, "Need at least one published item"
    for it in items:
        assert it.get("publisher_brand") == BRAND


# ---------- Media serving ----------
def test_existing_generated_image_served_200(session):
    items = _list(session, "Rewritten_Pending_Publish")
    with_img = [i for i in items if i.get("image_url") and i.get("image_status") == "generated"]
    assert with_img, "Expected a pre-generated rewritten item (3aa2e5e8...)"
    url = f"{BASE_URL}{with_img[0]['image_url']}"
    r = session.get(url, timeout=20)
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("image/jpeg")
    assert len(r.content) > 1000  # non-trivial image bytes


@pytest.mark.parametrize("bad_name", ["..%2f..", "..%2Fetc%2Fpasswd", "foo%2Fbar.jpg"])
def test_media_path_traversal_blocked(session, bad_name):
    r = session.get(f"{API}/media/{bad_name}", timeout=15)
    assert r.status_code in (400, 404), f"traversal '{bad_name}' not blocked: {r.status_code}"


def test_media_missing_file_returns_404(session):
    r = session.get(f"{API}/media/nonexistent-xyz-12345.jpg", timeout=15)
    assert r.status_code == 404


# ---------- Policy: image only after rewrite approval ----------
def test_generate_image_on_pending_returns_400(session):
    # create a fresh pending item
    created = session.post(
        f"{API}/news",
        json={
            "headline": "TEST_ pending image policy",
            "content": "TEST_ content for pending-image policy test (should reject image generation).",
            "category": "National",
            "source": "TEST",
            "source_language": "en",
        },
        timeout=15,
    ).json()
    item_id = created["id"]
    try:
        r = session.post(f"{API}/news/{item_id}/generate-image", timeout=20)
        assert r.status_code == 400
        assert "rewrite" in r.json().get("detail", "").lower()
    finally:
        session.delete(f"{API}/news/{item_id}", timeout=15)


def test_generate_image_on_nonexistent_returns_404(session):
    r = session.post(f"{API}/news/does-not-exist-xyz/generate-image", timeout=20)
    assert r.status_code == 404


# ---------- ONE real image generation ----------
def test_generate_image_on_rewritten_item_once(session):
    """Trigger ACTUAL Nano Banana generation exactly once on a rewritten item without image."""
    items = _list(session, "Rewritten_Pending_Publish")
    target = next((i for i in items if not i.get("image_url")), None)
    if not target:
        pytest.skip("No rewritten item without image available to test generation")

    r = session.post(f"{API}/news/{target['id']}/generate-image", timeout=120)
    assert r.status_code == 200, f"generate-image failed: {r.status_code} {r.text}"
    data = r.json()
    assert data["image_status"] == "generated"
    assert data["image_url"].startswith("/api/media/")
    assert data["image_url"].endswith(".jpg")
    assert data["publisher_brand"] == BRAND

    # Verify media is actually served
    r2 = session.get(f"{BASE_URL}{data['image_url']}", timeout=20)
    assert r2.status_code == 200
    assert r2.headers.get("content-type", "").startswith("image/jpeg")
    assert len(r2.content) > 1000
