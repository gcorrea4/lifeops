"""Mocked transport tests: chat extraction never parses model JSON."""

import sys
from types import ModuleType
from unittest.mock import Mock

import pytest

from app.ai.provider import ProviderError, WatsonxProvider


@pytest.fixture
def chat_model(monkeypatch):
    sdk = ModuleType("ibm_watsonx_ai")
    sdk.APIClient = Mock()
    sdk.Credentials = Mock()
    models = ModuleType("ibm_watsonx_ai.foundation_models")
    model = Mock()
    models.ModelInference = Mock(return_value=model)
    monkeypatch.setitem(sys.modules, "ibm_watsonx_ai", sdk)
    monkeypatch.setitem(sys.modules, "ibm_watsonx_ai.foundation_models", models)
    return model


def test_chat_requests_json_and_returns_content_without_parsing(chat_model):
    # Malformed JSON must reach the agent unchanged for its existing fallback.
    content = '{"reason_codes": [EARLIEST_SLOT]}'
    chat_model.chat.return_value = {"choices": [{"message": {"content": content}}]}

    assert WatsonxProvider().complete("exact planner prompt") == content
    chat_model.chat.assert_called_once_with(
        messages=[{"role": "user", "content": "exact planner prompt"}],
        params={
            "temperature": 0,
            "max_tokens": 512,
            "response_format": {"type": "json_object"},
        },
    )
    chat_model.generate_text.assert_not_called()


@pytest.mark.parametrize("response", [
    None, "unexpected", {}, {"choices": []},
    {"choices": [{"message": {"content": None}}]},
    {"choices": [{"message": {"content": [{"text": "unexpected"}]}}]},
])
def test_chat_rejects_missing_string_content(chat_model, response):
    chat_model.chat.return_value = response
    with pytest.raises(ProviderError, match="missing string message content"):
        WatsonxProvider().complete("prompt")


def test_chat_api_failure_remains_provider_error(chat_model):
    chat_model.chat.side_effect = RuntimeError("upstream unavailable")
    with pytest.raises(ProviderError, match="watsonx completion failed"):
        WatsonxProvider().complete("prompt")
