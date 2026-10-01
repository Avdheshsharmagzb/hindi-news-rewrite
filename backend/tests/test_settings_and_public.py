"""Tests for new features: /api/settings, /api/public/news, regenerate-image."""
import os
import pytest
import requests

BASE_URL = os.environ['REACT_APP_BACKEND_URL'].rstrip('/')
API = f"{BASE_URL}/api"


# ---------------- Settings ----------------
class TestSettings:
    def test_get_settings_defaults_or_persisted(self):
        r = requests.get(f"{API}/settings", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "watermark_position" in d
        assert "watermark_opacity" in d
        assert d["watermark_position"] in ("center", "bottom-right", "bottom-left")
        assert 5 <= int(d["watermark_opacity"]) <= 100

    def test_put_settings_persists(self):
        payload = {"watermark_position": "bottom-right", "watermark_opacity": 85}
        r = requests.put(f"{API}/settings", json=payload, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["watermark_position"] == "bottom-right"
        assert d["watermark_opacity"] == 85
        # GET verifies persistence
        g = requests.get(f"{API}/settings", timeout=15).json()
        assert g["watermark_position"] == "bottom-right"
        assert g["watermark_opacity"] == 85

    def test_put_settings_invalid_position_400(self):
        r = requests.put(f"{API}/settings",
                         json={"watermark_position": "top", "watermark_opacity": 50},
                         timeout=15)
        assert r.status_code == 400

    def test_put_settings_opacity_clamped(self):
        # Too low -> clamp to 5
        r = requests.put(f"{API}/settings",
                         json={"watermark_position": "center", "watermark_opacity": 1},
                         timeout=15)
        assert r.status_code == 200
        assert r.json()["watermark_opacity"] == 5
        # Too high -> clamp to 100
        r = requests.put(f"{API}/settings",
                         json={"watermark_position": "center", "watermark_opacity": 500},
                         timeout=15)
        assert r.status_code == 200
        assert r.json()["watermark_opacity"] == 100

    def test_put_settings_bottom_left_ok(self):
        r = requests.put(f"{API}/settings",
                         json={"watermark_position": "bottom-left", "watermark_opacity": 60},
                         timeout=15)
        assert r.status_code == 200
        assert r.json()["watermark_position"] == "bottom-left"


# ---------------- Public News ----------------
class TestPublicNews:
    def test_public_news_only_published_and_no_source(self):
        r = requests.get(f"{API}/public/news", timeout=15)
        assert r.status_code == 200
        items = r.json()
        assert isinstance(items, list)
        assert len(items) >= 1  # seed data has at least 1 published item
        allowed = {"id", "category", "headline", "content", "image_url",
                   "publisher_brand", "published_at"}
        for it in items:
            # Required keys present
            for k in allowed:
                assert k in it, f"missing key {k} in public item: {it.keys()}"
            # Forbidden keys absent
            assert "source" not in it
            assert "source_url" not in it
            assert "status" not in it  # should not leak internal status
            assert it["publisher_brand"] == "गाजियाबाद टाइम्स"

    def test_public_news_headline_is_rewritten(self):
        # Cross-check with admin GET /api/news (filter Published) that
        # public headline/content equals rewritten_* when available.
        pub = requests.get(f"{API}/public/news", timeout=15).json()
        admin = requests.get(f"{API}/news", params={"status": "Published"}, timeout=15).json()
        amap = {a["id"]: a for a in admin}
        for p in pub:
            a = amap.get(p["id"])
            assert a is not None, f"public id {p['id']} not found in admin"
            expected_h = a.get("rewritten_headline") or a.get("headline")
            expected_c = a.get("rewritten_content") or a.get("content")
            assert p["headline"] == expected_h
            assert p["content"] == expected_c


# ---------------- Regression ----------------
class TestRegression:
    def test_media_traversal_guard(self):
        for name in ["../etc/passwd", "..\\x.jpg", "foo/bar.jpg"]:
            r = requests.get(f"{API}/media/{name}", timeout=10)
            assert r.status_code in (400, 404)

    def test_cron_unauth(self):
        r = requests.post(f"{API}/cron/fetch-news", timeout=15)
        assert r.status_code == 401

    def test_cron_auth_ok(self):
        secret = os.environ.get("WEBHOOK_CRON_SECRET") or \
            "9f3c7a1e8b4d26f05c9a1be73d84f6029a7c15e2b8c0d1a6"
        r = requests.post(f"{API}/cron/fetch-news",
                          headers={"Authorization": f"Bearer {secret}"},
                          timeout=15)
        assert r.status_code == 200
        assert r.json().get("accepted") is True

    def test_generate_image_400_on_pending(self):
        # Pick a Pending_Review item and verify generate-image is rejected
        pending = requests.get(f"{API}/news", params={"status": "Pending_Review"},
                               timeout=15).json()
        if not pending:
            pytest.skip("No pending items")
        r = requests.post(f"{API}/news/{pending[0]['id']}/generate-image", timeout=20)
        assert r.status_code == 400

    def test_generate_image_404_on_unknown(self):
        r = requests.post(f"{API}/news/nonexistent-id/generate-image", timeout=20)
        assert r.status_code == 404

    def test_publish_requires_rewritten(self):
        pending = requests.get(f"{API}/news", params={"status": "Pending_Review"},
                               timeout=15).json()
        if not pending:
            pytest.skip("No pending items")
        r = requests.post(f"{API}/news/{pending[0]['id']}/publish", timeout=15)
        assert r.status_code == 400


# ---------------- Cost-controlled regenerate (ONCE) ----------------
class TestRegenerateOnce:
    """Trigger EXACTLY ONE real Nano Banana regeneration on a published/rewritten
    item that already has an image_url, verify image_url changes and status=generated."""

    def test_regenerate_once(self):
        # Prefer a published item with image_url; else rewritten with image_url
        for status in ("Published", "Rewritten_Pending_Publish"):
            items = requests.get(f"{API}/news", params={"status": status}, timeout=15).json()
            cand = next((i for i in items if i.get("image_url")), None)
            if cand:
                break
        else:
            pytest.skip("No item with image_url to regenerate (cost-safe skip)")

        before = cand["image_url"]
        r = requests.post(f"{API}/news/{cand['id']}/generate-image", timeout=120)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["image_status"] == "generated"
        assert d["image_url"].startswith("/api/media/")
        assert d["image_url"] != before  # new file
        # Verify served
        media_name = d["image_url"].split("/api/media/")[-1]
        g = requests.get(f"{API}/media/{media_name}", timeout=20)
        assert g.status_code == 200
        assert g.headers.get("content-type", "").startswith("image/")
