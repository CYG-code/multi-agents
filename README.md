# multi-agents

## Backend Setup (Windows PowerShell)
```powershell
cd d:\Projects\multi-agents\backend
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
alembic upgrade head
python -m uvicorn app.main:app --reload --port 8000
```

## Frontend Setup
```powershell
cd d:\Projects\multi-agents\frontend
npm install
npm run dev
```

## Environment Files
- `backend/.env.example`: template committed to repo
- `backend/.env`: local runtime config (do not commit)

Create local config:
```powershell
cd d:\Projects\multi-agents\backend
Copy-Item .env.example .env
```

## Relay API Configuration (yunwu.ai)
Recommended config in `backend/.env`:
```env
LLM_PROVIDER=openai_compatible
AI_API_KEY=your_token_here
AI_BASE_URL=https://yunwu.ai/v1
AGENT_MODEL=selected_model_name
DEBUG=true
```

Notes:
- `AI_BASE_URL` should use `/v1` for OpenAI-compatible SDK calls.
- If you accidentally set `https://yunwu.ai` or `https://yunwu.ai/v1/chat/completions`,
  code now auto-normalizes it to `https://yunwu.ai/v1`.

## Quick Relay Connectivity Test
```powershell
cd d:\Projects\multi-agents\backend
$env:RUN_RELAY_API_TEST='1'
python -m pytest tests/integration/test_relay_api_connection.py -q
```

Expected result:
- `1 passed` means relay connectivity + streaming generation are both working.

## Local/LAN Quick Switch
Use one command to start both backend and frontend:

```powershell
cd d:\Projects\multi-agents
.\start-dev.ps1        # local mode (127.0.0.1)
.\start-dev.ps1 -Lan   # LAN mode (0.0.0.0)
```

You can also run each side separately:

```powershell
# backend
cd d:\Projects\multi-agents\backend
.\start.ps1
.\start.ps1 -Lan

# frontend
cd d:\Projects\multi-agents\frontend
npm run dev
npm run dev:lan
```
