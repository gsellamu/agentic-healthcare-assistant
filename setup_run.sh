#!/usr/bin/env bash
# Setup and run — Agentic Healthcare Assistant (macOS / Linux)
# Usage:  bash setup_run.sh
# Run from the repository root.

set -e

echo "== Agentic Healthcare Assistant — setup =="

# 1. Create / activate virtual environment
if [ ! -d "venv" ]; then
    echo "Creating virtual environment (venv)..."
    python3 -m venv venv
fi
source venv/bin/activate

# 2. Install dependencies
echo "Installing dependencies (first run downloads torch + embedding model, a few minutes)..."
pip install --upgrade pip >/dev/null
pip install -r requirements.txt

# 3. Smoke test — confirms the package loads and the agent runs offline
echo ""
echo "== Smoke test =="
python -c "import sys; sys.path.insert(0,'src'); sys.path.insert(0,'config'); from hcasst.tools.records import RecordsManager; print('Patients loaded:', len(RecordsManager().list_patients()))"
python -c "import sys; sys.path.insert(0,'src'); sys.path.insert(0,'config'); from hcasst.agent.graph import HealthAssistant; s=HealthAssistant().run('Summarize history and book a nephrologist.', patient_hint='seed-001'); print('Agent OK:', s['response'][:60])"

# 4. Launch the dashboard
echo ""
echo "== Launching Streamlit dashboard (Ctrl+C to stop) =="
streamlit run app/streamlit_app.py
