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
    
    # Edit the values accordingly with reference to uat1
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

## Step 8: Audit log columns (only if your MySQL account cannot ALTER TABLE)

The call-log views read the request/response headers from `api_call_log`. Those
columns are added by an additive migration:

```bash
cd mapper_new
source venv/bin/activate
python -m backend.migrations.add_call_log_headers --check   # report what is missing
python -m backend.migrations.add_call_log_headers           # add them
```

If the MySQL user has no `ALTER` privilege this fails, and the log views used to
fail with it (`Unknown column 'api_call_log.source_request_headers'`). They no
longer do: the service inspects the table on startup, reads and writes only the
columns that exist, and takes the headers, query string and captured log from
MongoDB instead. It logs which columns it found missing at startup.

For that fallback to work, MongoDB must be reachable and configured. These three
settings are **required** — the service will not start without them, because a
built-in `localhost` default would connect to the wrong place and leave every
detail block silently empty:

```
AUDIT_MONGO_URI=mongodb://<host>:27017/
AUDIT_MONGO_DATABASE=gateway_logs_db
AUDIT_MONGO_COLLECTION=api_gateway_logs
```

When the columns are missing, this backend also writes its own calls to that
collection, stamped with the row id, so **new** calls are detailed too and not
just the ones the legacy gateway logged. This is automatic; `AUDIT_MONGO_MIRROR`
forces it on or off.

Running the migration later is still worthwhile — it makes MySQL the authority
again and stops the service depending on MongoDB for the detail — but the log
views work either way.