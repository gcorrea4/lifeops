"""
AI provider abstraction.

AbstractProvider defines the interface.
WatsonxProvider wraps the IBM watsonx AI SDK (lazy import — not required at module level).
MockProvider is for tests only and must never be used in production.
get_provider() is a FastAPI dependency that selects the active provider from settings.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.core.settings import settings


class ProviderError(Exception):
    """Raised by a provider when the upstream call fails."""


class ConfigurationError(Exception):
    """Raised when the AI_PROVIDER setting contains an unrecognised value."""


class AbstractProvider(ABC):
    """Minimal interface every AI provider must implement."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable name of this provider (e.g. 'watsonx', 'mock').

        Used exclusively for audit persistence — never for routing logic.
        """

    @property
    @abstractmethod
    def model_id(self) -> str:
        """Model identifier used by this provider instance.

        For WatsonxProvider this is settings.WATSONX_MODEL_ID.
        For MockProvider this is the literal string 'mock'.
        Used exclusively for audit persistence.
        """

    @abstractmethod
    def complete(self, prompt: str) -> str:
        """Send *prompt* to the model and return the raw string response."""


class WatsonxProvider(AbstractProvider):
    """
    IBM watsonx AI provider.

    Credentials and model are read exclusively from environment variables via
    settings — nothing is hardcoded here.

    The ibm-watsonx-ai SDK is imported lazily inside complete() so that the
    module can be imported without the SDK installed (e.g. when tests use
    MockProvider).
    """

    @property
    def provider_name(self) -> str:
        return "watsonx"

    @property
    def model_id(self) -> str:
        return settings.WATSONX_MODEL_ID

    def complete(self, prompt: str) -> str:
        try:
            # Lazy import: only loaded when WatsonxProvider is actually used.
            from ibm_watsonx_ai import APIClient, Credentials  # type: ignore
            from ibm_watsonx_ai.foundation_models import ModelInference  # type: ignore
        except ImportError as exc:
            raise ProviderError(
                "ibm-watsonx-ai is not installed. "
                "Add it to requirements.txt and re-install."
            ) from exc

        try:
            credentials = Credentials(
                url=settings.WATSONX_URL,
                api_key=settings.WATSONX_API_KEY,
            )
            client = APIClient(credentials=credentials)
            model = ModelInference(
                model_id=settings.WATSONX_MODEL_ID,
                api_client=client,
                project_id=settings.WATSONX_PROJECT_ID,
                params={"temperature": 0, "max_new_tokens": 512},
            )
            response = model.generate_text(prompt=prompt)
            return response
        except Exception as exc:
            raise ProviderError(f"watsonx completion failed: {exc}") from exc


class MockProvider(AbstractProvider):
    """
    Deterministic provider for tests.

    Pass *fixed_response* at construction time; every call to complete()
    returns it unchanged regardless of the prompt.
    """

    def __init__(self, fixed_response: str) -> None:
        self._response = fixed_response

    @property
    def provider_name(self) -> str:
        return "mock"

    @property
    def model_id(self) -> str:
        return "mock"

    def complete(self, prompt: str) -> str:  # noqa: ARG002
        return self._response


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------

def get_provider() -> AbstractProvider:
    """
    FastAPI dependency that returns the active AbstractProvider instance.

    Selection is driven by settings.AI_PROVIDER:
      "mock"    -> MockProvider (returns empty JSON object; tests instantiate directly)
      "watsonx" -> WatsonxProvider

    Any other value raises ConfigurationError at startup time — there is no silent
    fallback to MockProvider for unknown names.

    Tests override this dependency via app.dependency_overrides[get_provider].
    """
    provider_name = settings.AI_PROVIDER.lower()
    if provider_name == "mock":
        return MockProvider(fixed_response="{}")
    if provider_name == "watsonx":
        return WatsonxProvider()
    raise ConfigurationError(
        f"Unknown AI_PROVIDER value: {settings.AI_PROVIDER!r}. "
        "Supported values: 'mock', 'watsonx'."
    )
