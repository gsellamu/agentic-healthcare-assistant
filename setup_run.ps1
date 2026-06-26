# Setup and run — Agentic Healthcare Assistant (Windows / PowerShell)
# Usage:  .\setup_run.ps1
# Run from the repository root.

$ErrorActionPreference = "Stop"

Write-Host "== Agentic Healthcare Assistant — setup ==" -ForegroundColor Cyan

# 1. Create / activate virtual environment
if (-not (Test-Path "venv")) {
    Write-Host "Creating virtual environment (venv)..." -ForegroundColor Yellow
    python -m venv venv
}
. .\venv\Scripts\Activate.ps1

# 2. Install dependencies
Write-Host "Installing dependencies (first run downloads torch + embedding model, a few minutes)..." -ForegroundColor Yellow
pip install --upgrade pip | Out-Null
pip install -r requirements.txt

# 3. Smoke test — confirms the package loads and the agent runs offline
Write-Host "`n== Smoke test ==" -ForegroundColor Cyan
python -c "import sys; sys.path.insert(0,'src'); sys.path.insert(0,'config'); from hcasst.tools.records import RecordsManager; print('Patients loaded:', len(RecordsManager().list_patients()))"
python -c "import sys; sys.path.insert(0,'src'); sys.path.insert(0,'config'); from hcasst.agent.graph import HealthAssistant; s=HealthAssistant().run('Summarize history and book a nephrologist.', patient_hint='seed-001'); print('Agent OK:', s['response'][:60])"

# 4. Launch the dashboard
Write-Host "`n== Launching Streamlit dashboard (Ctrl+C to stop) ==" -ForegroundColor Cyan
streamlit run app/streamlit_app.py
