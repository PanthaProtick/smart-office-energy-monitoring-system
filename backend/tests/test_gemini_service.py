"""Unit tests for GeminiService.

These never make a real network call: with no GEMINI_API_KEY set, the
service falls back to templates by design; where we test the "Gemini
succeeded" and "Gemini failed" paths, we inject a fake client rather than
talking to the real API.
"""

import pytest

from app.services.gemini_service import GeminiService


@pytest.fixture
def no_key_service(monkeypatch):
    """A GeminiService guaranteed to have no client -- exercises the fallback path."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    return GeminiService(api_key=None)


class _FakeResponse:
    def __init__(self, text):
        self.text = text


class _FakeModels:
    def __init__(self, text=None, exc=None):
        self._text = text
        self._exc = exc
        self.last_call = None

    def generate_content(self, model, contents, config):
        self.last_call = {"model": model, "contents": contents, "config": config}
        if self._exc is not None:
            raise self._exc
        return _FakeResponse(self._text)


class _FakeClient:
    def __init__(self, text=None, exc=None):
        self.models = _FakeModels(text=text, exc=exc)


# ---------------------------------------------------------------------------
# Fallback behavior (no client configured at all)
# ---------------------------------------------------------------------------

def test_no_api_key_means_unavailable(no_key_service):
    assert no_key_service.is_available is False


def test_alert_message_fallback_matches_milestone_example(no_key_service):
    alert_data = {
        "alert_type": "AFTER_HOURS",
        "room": "Drawing Room",
        "active_devices": ["Fan 1", "Fan 2", "Light 1"],
        "time": "21:30",
    }
    result = no_key_service.generate_alert_message(alert_data)
    assert "Drawing Room" in result
    assert "Fan 1" in result and "Fan 2" in result and "Light 1" in result
    assert "21:30" in result


def test_alert_message_fallback_handles_empty_dict(no_key_service):
    # Must never raise, even with nothing supplied.
    result = no_key_service.generate_alert_message({})
    assert isinstance(result, str)
    assert result  # non-empty


def test_status_summary_fallback(no_key_service):
    result = no_key_service.generate_status_summary(
        {"total_devices": 12, "active_devices": 5, "total_rooms": 4, "active_rooms": 1}
    )
    assert "5" in result and "12" in result


def test_power_summary_fallback(no_key_service):
    result = no_key_service.generate_power_summary(
        {"total_power": 620.5, "total_power_usage_wh": 1830.2, "predicted_power_usage_wh": 7300.0}
    )
    assert "620.5" in result


def test_office_analysis_fallback(no_key_service):
    result = no_key_service.generate_office_analysis(
        {"total_power": 620.5, "active_rooms": 1, "total_rooms": 4, "active_alerts": 2}
    )
    assert "2" in result


def test_fallback_never_crashes_on_missing_keys(no_key_service):
    # Every method should degrade gracefully with a dict missing all expected keys.
    assert isinstance(no_key_service.generate_alert_message({"unexpected": "field"}), str)
    assert isinstance(no_key_service.generate_status_summary({}), str)
    assert isinstance(no_key_service.generate_power_summary({}), str)
    assert isinstance(no_key_service.generate_office_analysis({}), str)


# ---------------------------------------------------------------------------
# Success path: Gemini responds normally
# ---------------------------------------------------------------------------

def test_uses_gemini_response_when_available():
    svc = GeminiService(api_key="fake-key-for-test")
    svc._client = _FakeClient(text="  A concise AI-generated summary.  ")

    result = svc.generate_alert_message({"alert_type": "AFTER_HOURS", "room": "Drawing Room"})

    assert result == "A concise AI-generated summary."  # stripped of whitespace


def test_prompt_includes_supplied_data():
    svc = GeminiService(api_key="fake-key-for-test")
    fake_client = _FakeClient(text="ok")
    svc._client = fake_client

    svc.generate_alert_message({"alert_type": "AFTER_HOURS", "room": "Server Room"})

    assert "Server Room" in fake_client.models.last_call["contents"]
    assert "AFTER_HOURS" in fake_client.models.last_call["contents"]


def test_empty_gemini_response_falls_back_to_template():
    svc = GeminiService(api_key="fake-key-for-test")
    svc._client = _FakeClient(text="   ")  # whitespace-only

    result = svc.generate_alert_message({"alert_type": "AFTER_HOURS", "room": "Drawing Room"})

    assert "Drawing Room" in result  # came from the fallback template, not Gemini


# ---------------------------------------------------------------------------
# Failure path: Gemini errors, times out, or the SDK raises -- must never crash
# ---------------------------------------------------------------------------

def test_api_exception_falls_back_without_raising():
    svc = GeminiService(api_key="fake-key-for-test")
    svc._client = _FakeClient(exc=TimeoutError("simulated timeout"))

    result = svc.generate_alert_message(
        {"alert_type": "AFTER_HOURS", "room": "Drawing Room", "time": "21:30"}
    )

    # Falls back to the deterministic template -- still useful, never raises.
    assert "Drawing Room" in result
    assert "21:30" in result


def test_api_exception_logs_the_error(caplog):
    import logging

    svc = GeminiService(api_key="fake-key-for-test")
    svc._client = _FakeClient(exc=RuntimeError("boom"))

    with caplog.at_level(logging.ERROR):
        svc.generate_power_summary({"total_power": 100.0})

    assert any("Gemini API call failed" in record.message for record in caplog.records)


def test_missing_package_degrades_to_fallback(monkeypatch):
    """Simulates google-genai not being importable at all."""
    import app.services.gemini_service as mod

    monkeypatch.setattr(mod, "_GENAI_IMPORT_ERROR", ImportError("simulated: package missing"))
    svc = GeminiService(api_key="some-key")

    assert svc.is_available is False
    assert isinstance(svc.generate_alert_message({"alert_type": "TEST"}), str)


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

def test_get_gemini_service_returns_same_instance():
    from app.services.gemini_service import get_gemini_service

    first = get_gemini_service()
    second = get_gemini_service()
    assert first is second
