"""Disease-information search over trusted sources.

Core build uses a small offline knowledge base so the agent always has
grounded, citable content with no network. Every result is a typed
SearchResult carrying its own citation — the zero-hallucination bar applied
to external data. (A live MedlinePlus/PubMed backend is a stretch add-on.)
"""

from __future__ import annotations

from config.settings import Settings, get_settings
from hcasst.models import SearchResult

# Minimal curated KB so demos/tests have grounded, cited content.
_OFFLINE_KB: dict[str, str] = {
    "chronic kidney disease": (
        "Management focuses on slowing progression: control blood pressure "
        "(ACE inhibitors/ARBs are renoprotective), manage diabetes, restrict "
        "dietary sodium/protein as advised, avoid nephrotoxic drugs (e.g. NSAIDs), "
        "and monitor eGFR and albuminuria. SGLT2 inhibitors are increasingly used "
        "to slow CKD progression in diabetic kidney disease."
    ),
    "atrial fibrillation": (
        "Treatment targets stroke prevention with anticoagulation (e.g. DOACs such "
        "as apixaban) guided by CHA2DS2-VASc risk, plus rate or rhythm control."
    ),
    "diabetes": (
        "Type 2 diabetes care centers on lifestyle, metformin first-line, and "
        "agents such as GLP-1 receptor agonists and SGLT2 inhibitors with "
        "cardiovascular and renal benefit; HbA1c targets are individualized."
    ),
}


class DiseaseSearch:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def search(self, topic: str, max_results: int = 4) -> list[SearchResult]:
        """Return citable disease-information snippets for a topic."""
        key = next((k for k in _OFFLINE_KB if k in topic.lower()), None)
        if key:
            return [
                SearchResult(
                    source="OfflineKB",
                    title=key.title(),
                    snippet=_OFFLINE_KB[key],
                    url="https://medlineplus.gov/",
                    citation="[OfflineKB]",
                )
            ]
        return [
            SearchResult(
                source="OfflineKB",
                title=topic.title(),
                snippet=(
                    "Topic not in the offline knowledge base. Consult MedlinePlus "
                    "or a clinician for authoritative guidance."
                ),
                url="https://medlineplus.gov/",
                citation="[OfflineKB]",
            )
        ]
    