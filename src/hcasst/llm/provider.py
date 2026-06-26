"""LLM provider: real Anthropic Claude with a deterministic offline fallback.

Every model call in the project goes through `get_llm()`, which returns either
ClaudeLLM (real) or MockLLM (offline) based on `settings.llm_available`.
"""
from __future__ import annotations
import json
import re
from typing import Any, Protocol

from config.settings import Settings, get_settings


class LLM(Protocol):
    name: str
    def complete(self, system: str, user: str) -> str: ...
    def complete_json(self, system: str, user: str) -> Any: ...


def _extract_json(text: str) -> Any:
    """Best-effort parse of JSON embedded in model text."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    for opener, closer in (("{", "}"), ("[", "]")):
        start, end = text.find(opener), text.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                continue
    raise ValueError(f"Could not parse JSON from model output: {text[:200]!r}")
class ClaudeLLM:
    """Wrapper over langchain-anthropic's ChatAnthropic."""
    name = "claude"

    def __init__(self, settings: Settings) -> None:
        from langchain_anthropic import ChatAnthropic

        kwargs: dict[str, Any] = {
            "model": settings.model,
            "api_key": settings.anthropic_api_key,
            "max_tokens": settings.max_tokens,
        }
        # Opus 4.7+ reject temperature/top_p/top_k (400). Only send temperature
        # to models that still accept it.
        if not self._rejects_temperature(settings.model):
            kwargs["temperature"] = settings.temperature

        self._client = ChatAnthropic(**kwargs)

    @staticmethod
    def _rejects_temperature(model: str) -> bool:
        """Newer Opus models (4.7, 4.8+) reject the temperature parameter."""
        return bool(re.search(r"opus-4-[78]", model))

    def complete(self, system: str, user: str) -> str:
        msg = self._client.invoke([("system", system), ("human", user)])
        content = msg.content
        if isinstance(content, list):
            content = "".join(
                b.get("text", "") if isinstance(b, dict) else str(b) for b in content
            )
        return str(content).strip()

    def complete_json(self, system: str, user: str) -> Any:
        sys2 = system + "\n\nRespond with ONLY valid JSON. No prose, no code fences."
        return _extract_json(self.complete(sys2, user))

class MockLLM:
    """Deterministic offline stand-in. Reads a `[task:NAME]` hint from the
    system prompt so each agent node gets a structurally valid response."""
    name = "mock"

    @staticmethod
    def _task(system: str) -> str:
        m = re.search(r"\[task:([a-z_]+)\]", system)
        return m.group(1) if m else "generic"

    def complete(self, system: str, user: str) -> str:
        task = self._task(system)
        if task == "summary":
            return (
                "Summary (offline mode): statements below are drawn from the "
                "provided evidence [E1]. Connect an ANTHROPIC_API_KEY for a "
                "clinically richer summary."
            )
        if task == "disease":
            return (
                "Disease information (offline mode): see the cited source snippets "
                "below for current guidance [OfflineKB]. Connect an "
                "ANTHROPIC_API_KEY for a synthesized, clinically richer answer."
            )
        return f"Offline MockLLM response. (echoing intent: {user[:160]})"

    def complete_json(self, system: str, user: str) -> Any:
        if self._task(system) == "planner":
            return self._plan(user)
        if self._task(system) == "grounding":
            return {"grounded": True, "uncited_claims": [], "rationale": "offline: citations present"}
        if self._task(system) == "qaeval":
            return {"grade": "CORRECT", "score": 1.0, "rationale": "offline: heuristic pass"}
        
        return {"result": "offline", "input": user[:160]}

    @staticmethod
    def _plan(user: str) -> dict[str, Any]:
        """Decompose intent into sub-goals via keyword heuristics."""
        text = user.lower()
        steps: list[dict[str, str]] = [
            {"goal": "Identify patient and retrieve context", "tool": "get_patient_history"}
        ]
        if any(k in text for k in ("book", "appointment", "schedule", "nephrolog", "cardiolog", "doctor")):
            steps.append({"goal": "Find and propose appointment slots", "tool": "book_appointment"})
        if any(k in text for k in ("summar", "history", "diagnos", "treatment", "record")):
            steps.append({"goal": "Summarize medical history with citations", "tool": "summarize_history"})
        if any(k in text for k in ("latest", "treatment", "disease", "research", "method")):
            steps.append({"goal": "Search trusted medical sources", "tool": "search_disease_info"})
        return {"intent": user.strip()[:200], "steps": steps}
    
_INSTANCE: LLM | None = None


def get_llm(settings: Settings | None = None, *, force_mock: bool = False) -> LLM:
    """Return a singleton LLM — Claude or MockLLM, chosen by config."""
    global _INSTANCE
    settings = settings or get_settings()
    if force_mock or not settings.llm_available:
        if not isinstance(_INSTANCE, MockLLM):
            _INSTANCE = MockLLM()
        return _INSTANCE
    if not isinstance(_INSTANCE, ClaudeLLM):
        try:
            _INSTANCE = ClaudeLLM(settings)
        except Exception as exc:
            print(f"[provider] Claude init failed ({exc}); using MockLLM")
            _INSTANCE = MockLLM()
    return _INSTANCE


def reset_llm() -> None:
    """Clear the cached instance (for tests / settings changes)."""
    global _INSTANCE
    _INSTANCE = None


