# CloudPilot SwitchOps — Local Development Setup Guide

## 1. Prerequisites

- **Operating System**: Windows, Linux, or macOS.
- **Python**: Python 3.11 (tested on CPython 3.11.9).
- **Package Manager**: [uv](https://docs.astral.sh/uv/) (recommended) or standard `pip`.
- **Switch AI**: Switch Console desktop app or Docker runtime (optional for local testing; the built-in emulated bridge handles offline development).

---

## 2. Setting Up the Virtual Environment

### Using `uv` (Fast & Isolated)
```powershell
# Create virtual environment with Python 3.11
uv venv --python 3.11 .venv

# Activate virtual environment
.venv\Scripts\activate

# Install Phase 1 dependencies
uv pip install fastapi uvicorn pydantic pydantic-settings pytest pytest-asyncio httpx websockets sqlalchemy boto3 networkx
```

### Using standard `python`
```powershell
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

---

## 3. Environment Configuration

Copy `.env.example` to `.env`:
```powershell
Copy-Item .env.example .env
```

Review and adjust settings in `.env`:
```env
CLOUDPILOT_ENVIRONMENT="development"
CLOUDPILOT_DATABASE_URL="sqlite:///./cloudpilot_tasks.db"
CLOUDPILOT_SWITCH_BRIDGE_URL="http://localhost:8080"
CLOUDPILOT_SWITCH_ROOM_ID="cloudpilot-ops"
```

*Note*: If `CLOUDPILOT_SWITCH_AGENT_API_KEY` is omitted, CloudPilot SwitchOps automatically boots with the internal **EmulatedSwitchBridge**, enabling full local testing without requiring external Docker containers or live Switch servers.

---

## 4. Running the Application

Start the FastAPI application with Uvicorn:
```powershell
.venv\Scripts\uvicorn.exe app.main:app --host 0.0.0.0 --port 8000 --reload
```

Verify service liveness:
```powershell
curl http://localhost:8000/health/live
```
Expected output:
```json
{
  "status": "healthy",
  "app_name": "CloudPilot SwitchOps",
  "app_version": "1.0.0",
  "uptime_seconds": 1.25,
  "timestamp": "2026-10-30T10:00:00Z"
}
```

Verify readiness:
```powershell
curl http://localhost:8000/health/ready
```
Expected output:
```json
{
  "status": "ready",
  "database": "healthy",
  "switch_integration": {
    "configured": false,
    "bridge_url": "http://localhost:8080",
    "status": "healthy"
  },
  "timestamp": "2026-10-30T10:00:00Z"
}
```

Interactive OpenAPI documentation is available at:
- `http://localhost:8000/docs`
- `http://localhost:8000/redoc`

---

## 5. Running Automated Tests

Run the full Phase 1 test suite:
```powershell
.venv\Scripts\pytest.exe tests -v
```

Run specific test layers:
```powershell
# Unit tests
.venv\Scripts\pytest.exe tests/unit -v

# Integration tests
.venv\Scripts\pytest.exe tests/integration -v

# Switch protocol contract tests
.venv\Scripts\pytest.exe tests/contract -v
```

Run preserved legacy platform foundation tests:
```powershell
.venv\Scripts\pytest.exe docker/tests/test_platform_foundation.py -v
```

---

## 6. Code Quality & Linting

Run Ruff code quality checks:
```powershell
ruff check app tests
```
