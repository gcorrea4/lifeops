"""
Credential-gated smoke test for WatsonxProvider.

This test is automatically skipped when WATSONX_API_KEY is not set in the
environment (the default for CI and local development without credentials).

To run against a real IBM watsonx endpoint, export the required variables:

    export WATSONX_API_KEY=...
    export WATSONX_PROJECT_ID=...
    export WATSONX_URL=https://us-south.ml.cloud.ibm.com
    export WATSONX_MODEL_ID=granite-4-1-8b
    export AI_PROVIDER=watsonx

Then run:

    pytest backend/tests/test_watsonx_provider.py -v -s
"""

from __future__ import annotations

import pytest

from app.core.settings import settings


# Skip the entire module when no real API key is present.
pytestmark = pytest.mark.skipif(
    not settings.WATSONX_API_KEY,
    reason="WATSONX_API_KEY not set — skipping live watsonx smoke test",
)


def test_watsonx_provider_returns_nonempty_string() -> None:
    """
    Verify that WatsonxProvider.complete() reaches the IBM watsonx endpoint
    and returns a non-empty string.

    Assertions are intentionally minimal: this is a connectivity smoke test,
    not a PlannerAgent contract test.  JSON structure is not asserted here.
    """
    from app.ai.provider import WatsonxProvider

    provider = WatsonxProvider()
    result = provider.complete('Return the word HELLO as JSON: {"word": "HELLO"}')

    assert isinstance(result, str), f"Expected str, got {type(result)}"
    assert len(result) > 0, "WatsonxProvider returned an empty string"
