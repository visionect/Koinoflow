import pytest
from django.test import RequestFactory
from django.urls import resolve


def test_root_resolves_to_spa_fallback():
    match = resolve("/")
    assert match.func.__name__ == "spa_fallback"


def test_deep_client_path_resolves_to_spa_fallback():
    match = resolve("/visionect/skills")
    assert match.func.__name__ == "spa_fallback"


def test_spa_fallback_view_returns_index_html():
    from config.urls import spa_fallback

    request = RequestFactory().get("/visionect/skills")
    response = spa_fallback(request)
    assert response.status_code == 200
    content = response.content.decode()
    assert '<div id="root"></div>' in content
    assert "<title>Koinoflow</title>" in content


def test_api_health_skips_throttles(api_client):
    """Regression: health must not inherit API-level throttles (Redis-backed)."""
    response = api_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
