# Implementation Guide

**The Setup** — how to install the assistant and connect it to its services.

## Prerequisites

- Python 3.11 or newer
- A shell (examples use Windows PowerShell)
- ~1 GB free disk (sentence-transformers + torch + the model cache)

## Install

```powershell
cd capstone
python -m venv venv311
venv311\Scripts\activate          # Windows  (source venv311/bin/activate on *nix)
pip install -r requirements.txt
```

The first run downloads the SentenceTransformer model `all-MiniLM-L6-v2`
(~80 MB), one time.

## Configure

Copy `.env.example` to `.env`:

```powershell
copy .env.example .env
```

Leave `ANTHROPIC_API_KEY` blank to run fully offline with the deterministic
MockLLM. Provide a key (or use the in-app sidebar toggle) to use real Claude.

```
ANTHROPIC_API_KEY=                 # blank = offline mock
HCASST_MODEL=claude-opus-4-8
HCASST_OFFLINE=false               # force offline even if a key is present
HCASST_USE_ST_EMBEDDINGS=true      # SentenceTransformer; false = hashing fallback
HCASST_MAX_LOOPS=3                 # grounding regenerate-or-caveat limit
```

## Run the dashboard

```powershell
streamlit run app/streamlit_app.py
```

Opens at http://localhost:8501. Stop with Ctrl+C. After any code change,
**fully restart** — Streamlit caches imports and resources, so a save-rerun is
not enough.

## Run evaluation (CLI)

```powershell
python -c "import sys; sys.path.insert(0,'src'); sys.path.insert(0,'config'); from hcasst.eval.runner import run_evaluation; print(run_evaluation()['metrics'])"
```

## External services (all keyless except Anthropic)

| Service | Endpoint | Auth |
|---------|----------|------|
| MedlinePlus | https://wsearch.nlm.nih.gov | none |
| PubMed E-utilities | https://eutils.ncbi.nlm.nih.gov | none |
| Anthropic API | https://api.anthropic.com | API key (optional) |

If the network is unavailable, disease search falls back to a curated offline
knowledge base, and embeddings fall back to the deterministic hashing embedder.

## Data and storage

- Seed patients: `data/seed/patients.json`
- SQLite DB (created on first use): `data/hcasst.db`
- FAISS indexes are built in memory per session.

## Security

- `.env` (which may hold a real key) is git-ignored — never commit it.
- Ship `.env.example` (no secret) instead.
- If a key is ever exposed, revoke it at console.anthropic.com and mint a new one.
