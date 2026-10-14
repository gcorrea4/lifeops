"""The explanation language option (en/pt): prompt instruction, localized fallback and HTTP contract.

Scheduling, candidates and reason codes must be identical regardless of the language.
"""

from __future__ import annotations

import json
from datetime import date, datetime

import pytest

from app.ai.agent import PlannerAgent
from app.ai.provider import AbstractProvider, MockProvider, get_provider
from app.ai.schemas import AgentInput, CandidateSlot, TaskSummary
from app.main import app

pytestmark = pytest.mark.usefixtures("fixed_now")

_VALID = json.dumps({"recommended_candidate_id": 0, "explanation": "Ok."})


class RecordingProvider(AbstractProvider):
    """Returns a valid answer and remembers the prompt it received."""

    provider_name = "recording"
    model_id = "recording"

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return _VALID


def _agent_input(language: str = "en") -> AgentInput:
    task = TaskSummary(id=1, title="Study", duration_minutes=60, priority="high", deadline=None, status="pending")
    slots = [CandidateSlot(start_datetime=datetime(2026, 10, 8, 8), end_datetime=datetime(2026, 10, 8, 9),
                           date=date(2026, 10, 8))]
    return AgentInput(task=task, candidate_slots=slots, language=language)


class TestPrompt:
    def test_english_prompt_has_no_language_line(self):
        provider = RecordingProvider()
        PlannerAgent(provider).recommend(_agent_input("en"))
        assert "Portuguese" not in provider.prompts[0]
        assert provider.prompts[0].endswith("outside the JSON object.")

    def test_portuguese_prompt_asks_for_brazilian_portuguese(self):
        provider = RecordingProvider()
        PlannerAgent(provider).recommend(_agent_input("pt"))
        assert provider.prompts[0].rstrip().endswith("Write the explanation in Brazilian Portuguese.")

    def test_default_language_is_english(self):
        assert _agent_input().language == "en"

    def test_model_contract_and_reason_codes_do_not_depend_on_language(self):
        recs = {lang: PlannerAgent(RecordingProvider()).recommend(_agent_input(lang)) for lang in ("en", "pt")}
        assert recs["en"].reason_codes == recs["pt"].reason_codes
        assert recs["en"].recommended_slot == recs["pt"].recommended_slot


class TestFallback:
    @pytest.mark.parametrize("language,expected", [
        ("en", "Default recommendation: first available valid slot selected."),
        ("pt", "Recomendação padrão: primeiro horário válido selecionado."),
    ])
    def test_fallback_explanation_is_localized(self, language, expected):
        recommendation = PlannerAgent(MockProvider("not json")).recommend(_agent_input(language))
        assert recommendation.fallback_used is True
        assert recommendation.explanation == expected
        assert [code.value for code in recommendation.reason_codes] == ["PROVIDER_FALLBACK"]


class TestHttp:
    @pytest.fixture()
    def provider(self):
        provider = RecordingProvider()
        app.dependency_overrides[get_provider] = lambda: provider
        yield provider
        del app.dependency_overrides[get_provider]

    def _task(self, client):
        return client.post("/api/v1/tasks/", json={"title": "T", "duration_minutes": 60, "priority": "medium"}).json()

    def test_language_reaches_the_prompt(self, client, provider):
        task = self._task(client)
        assert client.post("/api/v1/planner/recommend", json={"task_id": task["id"], "language": "pt"}).status_code == 201
        assert provider.prompts[-1].rstrip().endswith("Write the explanation in Brazilian Portuguese.")

    def test_language_is_optional(self, client, provider):
        task = self._task(client)
        assert client.post("/api/v1/planner/recommend", json={"task_id": task["id"]}).status_code == 201
        assert "Portuguese" not in provider.prompts[-1]

    def test_unknown_language_is_rejected(self, client, provider):
        task = self._task(client)
        response = client.post("/api/v1/planner/recommend", json={"task_id": task["id"], "language": "fr"})
        assert response.status_code == 422
        assert provider.prompts == []
