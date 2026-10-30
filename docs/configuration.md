# CloudPilot SwitchOps — Configuration Reference

## 1. Overview

CloudPilot SwitchOps uses a strongly typed configuration system built on **Pydantic Settings**.
Configuration values are loaded hierarchically with the following precedence (highest priority first):
1. Process environment variables prefixed with `CLOUDPILOT_`
2. `.env` file in project root
3. Default values defined in `app/core/config.py`

---

## 2. Configuration Settings Reference

| Environment Variable | Type | Default | Description |
|:---|:---|:---|:---|
| `CLOUDPILOT_APP_NAME` | string | `"CloudPilot SwitchOps"` | Display name of the application. |
| `CLOUDPILOT_APP_VERSION` | string | `"1.0.0"` | Semver application version. |
| `CLOUDPILOT_ENVIRONMENT` | enum | `"development"` | Runtime environment: `development`, `testing`, `staging`, `production`. |
| `CLOUDPILOT_DEBUG` | boolean | `false` | Enables debug mode. Accepts `true`, `1`, `yes`, `on`. |
| `CLOUDPILOT_HOST` | string | `"0.0.0.0"` | Server bind host. |
| `CLOUDPILOT_PORT` | integer | `8000` | Server listen port. |
| `CLOUDPILOT_CORS_ORIGINS` | list | `["*"]` | Allowed CORS origins. |
| `CLOUDPILOT_LOG_LEVEL` | string | `"INFO"` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`). |
| `CLOUDPILOT_LOG_FORMAT` | string | `"json"` | Log format: `"json"` (structured) or `"console"` (plain text). |
| `CLOUDPILOT_DATABASE_URL` | string | `"sqlite:///./cloudpilot_tasks.db"` | Persistence database URL (SQLite or PostgreSQL). |
| `CLOUDPILOT_SWITCH_BRIDGE_URL` | string | `"http://localhost:8080"` | Base URL of the Switch Agent Bridge. |
| `CLOUDPILOT_SWITCH_ROOM_ID` | string | `"cloudpilot-ops"` | Switch operations room ID to claim and monitor. |
| `CLOUDPILOT_SWITCH_AGENT_NAME` | string | `"cloudpilot-ops-agent"` | Name registered with Switch (`^[a-z0-9][a-z0-9._-]*$`). |
| `CLOUDPILOT_SWITCH_REGISTRATION_KEY`| SecretStr | `None` | Bearer token used for out-of-band `POST /agents` registration. |
| `CLOUDPILOT_SWITCH_AGENT_ID` | string | `None` | Pre-registered Switch agent UUID. |
| `CLOUDPILOT_SWITCH_AGENT_API_KEY` | SecretStr | `None` | Agent API key used for WebSocket connection and room messaging. |
| `CLOUDPILOT_SWITCH_HEARTBEAT_INTERVAL_SECONDS` | float | `2.0` | Target interval for replying to Switch server pings. |
| `CLOUDPILOT_SWITCH_HEARTBEAT_TIMEOUT_SECONDS` | float | `6.0` | Lapse timeout before Switch evicts inactive socket. |
| `CLOUDPILOT_SWITCH_AUTO_RECONNECT` | boolean | `true` | Enables automatic reconnection with generation fencing. |

---

## 3. Secret Protection & Sanitization

1. **`SecretStr` Masking**:
   - Sensitive fields (`switch_registration_key`, `switch_agent_api_key`) are stored as Pydantic `SecretStr`.
   - Calling `str(settings)` or printing the settings object automatically masks them as `**********`.
   - Accessing raw secrets requires explicit `.get_secret_value()`.

2. **Log Redaction**:
   - `app/core/logging.py` applies automated regex masking to all log lines.
   - Bearer tokens, API keys, and registration keys matching known token formats are automatically replaced with `[REDACTED]`.

3. **Safe Export**:
   - The `settings.safe_dict()` method exports diagnostic configuration for health probes and logs with credentials completely omitted.
