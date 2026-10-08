# MAPPER SETUP GUIDE

## Step 1: Clone the repo

```bash
git clone https://github.com/mudassirj-imis/mapper_new.git
```
## Step 2: Create virtual environment and install dependencies

```bash
    # Backend
    cd mapper_new
    python3 -m venv venv
    source venv/bin/activate
    pip install -r backend/requirements.txt

    # Frontend
    cd mapper_new/frontend
    npm install
    npm run build
```

## Step 3: Setup .env of both backend and frontend according to .env.example
```bash
    cd mapper_new
    cp .env.example .env
    cd mapper_new/frontend
    cp .env.example .env
    
    # Edit the values accordingly with reference to uat1 (MONGO VARIABLES STAY SAME)
```

## Step 4: Modify the path in ecosystem.config.js file

```bash
    cd mapper_new
    sudo nano ecosystem.config.js

    # Backend
    cwd: "/home/username/mapper_new", ## main.py location
    script: "/home/username/mapper_new/venv/bin/python", ## virtual environment location


    # Frontend
    cwd: "/home/username/mapper_new/frontend", ## frontend location
```
## Step 5: Start the server

```bash
    cd mapper_new
    pm2 start ecosystem.config.js
    pm2 save
    pm2 startup

    # Test
    pm2 logs mapper-frontend
    pm2 logs mapper-backend
```

## Step 6: Setup in kong 

```bash
    # Backend 
    curl -i -X POST http://localhost:8003/services \
    --data name=mapper-backend \
    --data protocol=http \
    --data host=172.17.0.1 \
    --data port=2528

    curl -i -X POST http://localhost:8003/services/mapper-backend/routes \
    --data name=mapper-backend-route \
    --data 'paths[]=/integration-backend' \ # This should match the APP_ROOT_PATH in backend .env
    --data strip_path=true \
    --data preserve_host=true

    # Frontend
    curl -i -X POST http://localhost:8003/services \
    --data name=mapper-frontend \
    --data protocol=http \
    --data host=172.17.0.1 \
    --data port=3005

    curl -i -X POST http://localhost:8003/services/mapper-frontend/routes \
    --data name=mapper-frontend-route \
    --data 'paths[]=/external-integration' \ # This should match the VITE_BASE_URL in frontend .env
    --data strip_path=false \
    --data preserve_host=true
```

## Step 7: Verify
Access with browser
```
https://<BASE_URL>:<PORT>/external-integration      # Frontend (PATH AS SET IN KONG AND VITE_BASE_URL in frontend .env)
https://<BASE_URL>:<PORT>/integration-backend/docs  # Backend (PATH AS SET IN KONG AND APP_ROOT_PATH in backend .env)
```
## Ports:
**Backend: 2528**  <br>
**Frontend: 3005**

## External log ingestion (CRM gateway helper)

Other services (e.g. the IMIS CRM `gatewayhelper`) can push their per-call
audit logs into this app instead of the legacy mapper. The logs are
credential-redacted, linked to their `api_endpoint` row (so they show up in
the dashboard), and stored in the same `api_call_log` MySQL table + audit
MongoDB collection the rest of the app uses.

**Endpoints** (no user login required; optional shared secret):

```
POST /api/call-logs/ingest
POST /api/call-logs              # alias, legacy mapper contract
```

**Headers**

```
Content-Type: application/json
X-Log-Ingest-Token: <value of LOG_INGEST_TOKEN>   # only if LOG_INGEST_TOKEN is set
```

**Body** — every field is optional; common aliases are understood:

```json
{
  "request_id": "3f6c1f2e-...)",
  "method": "POST",
  "path": "/v1/integration/cc/create-ticket",
  "endpoint_id": null,
  "success": true,
  "status": "SUCCESS",
  "status_code": 200,
  "external_status_code": 200,
  "total_time_ms": 412,
  "headers": {"Content-Type": "application/json"},
  "request_body": {"cnic": "12345-..."},
  "response": {"message": "created"},
  "error": null,
  "full_log": "optional captured console output"
}
```

Recognised aliases include `headers` / `internal_request_headers`,
`request_body` / `body` / `request_data`,
`response` / `response_body` / `source_response`,
`status_code` / `client_status_code`,
`response_time_ms` / `total_time_ms`, `error_message`, `requestId`,
`endpointId`, ... Unknown keys pass through untouched.

**Response**

```json
{"success": true, "message": "Call log stored", "log_id": 1234, "endpoint_id": 277}
```

**Example caller** (for the CRM `gatewayhelper.py` — wire it there, this repo
is the receiving end only):

```python
LOG_INGEST_URL = f"{os.getenv('GATEWAY_URL_2')}/api/call-logs/ingest"

def store_log(log_entry: dict) -> None:
    try:
        requests.post(LOG_INGEST_URL, json=log_entry, timeout=5)
    except Exception as exc:                      # logging must never break the call
        print(f"[LOG INGEST] {exc}")
```

Endpoint linking: the `path` is matched (newest first) against
`target_api_url`, then `source_api_url`, with the HTTP `method` as a
prefilter — the same suffix rule the gateway engine uses. If nothing matches,
the log is still stored, just without an endpoint link.

