"""Readiness must be honest and hosted mode must retain spending authorization."""

from fastapi.testclient import TestClient

from src.api.main import app
from src.config import get_settings


def test_readiness_reports_configuration_without_claiming_provider_verification(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("META_MODEL_API_KEY", "fake-provider-secret")
    monkeypatch.setenv("DEMO_KEY", "fake-unlock-secret")
    get_settings.cache_clear()
    response = TestClient(app).get("/api/v1/readiness")
    assert response.json() == {
        "default_mode": "saved",
        "live_unlock_configured": True,
        "provider_key_configured": True,
        "provider_verified": False,
    }
    assert "secret" not in response.text


def test_hosted_false_demo_mode_still_requires_live_authorization(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("DEMO_KEY", "test-unlock")
    get_settings.cache_clear()
    client = TestClient(app)
    assert client.get("/api/v1/readiness").json()["default_mode"] == "saved"
    response = client.post("/api/v1/transcribe-voice?live=true", json={"audio_base64": "AAAA"})
    assert response.status_code == 403
    assert client.post("/api/v1/transcribe-voice", json={"audio_base64": "AAAA"}).status_code == 403
