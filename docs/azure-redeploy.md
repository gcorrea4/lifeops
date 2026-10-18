# Azure redeploy runbook

How the public demo of LifeOps was hosted and how to bring it back after the Azure resources are deleted. No secrets are stored here: database and watsonx values come from the local, git-ignored files (`.env`, and the backups kept outside the repository).

The first deployment lived in the resource group `lifeops-rg` from 2026-10-13 to 2026-10-18 and was then deleted on purpose to stop the cost (the database was about US$0.49 per day). The frontend on Vercel (`https://boblifeops.vercel.app`) stayed online and shows a "back-end turned off" message while the API is gone.

## Architecture of the demo

| Part | Service | Notes |
|---|---|---|
| Frontend | Vercel (root directory `frontend`) | `frontend/vercel.json` rewrites `/api/*` to the API, so the browser never needs CORS |
| API | Azure App Service, Linux, Python 3.12, plan **F1 (Free)**, region **South Central US** | F1 quota was 0 in East US; no Always On; about 60 CPU minutes per day; cold start about 20 s |
| Database | Azure Database for MySQL Flexible Server, **Standard_B1ms (Burstable)**, MySQL 8.0, 20 GB, region East US | TLS is required (`require_secure_transport=ON`); database `lifeops` with `utf8mb4` / `utf8mb4_0900_ai_ci` |
| AI | IBM watsonx (au-syd), `meta-llama/llama-3-3-70b-instruct` | credentials come from the local `.env` |
| Keep-warm | Better Stack uptime monitor on `/health` every 3 minutes | optional; pause it when the API is down |

## 1. Create the resources

Always list what exists before retrying a failed or interrupted create: stopping the local `az` command does not cancel the server-side creation, and a duplicate paid server appeared once.

```bash
az group list -o table
az resource list -g lifeops-rg -o table
```

Names are random suffixes to be globally unique. Use new ones and note them down.

```bash
az group create -n lifeops-rg -l southcentralus

# App Service plan (free) and web app
az appservice plan create -g lifeops-rg -n lifeops-plan --is-linux --sku F1 -l southcentralus
az webapp create -g lifeops-rg -p lifeops-plan -n <APP_NAME> --runtime "PYTHON:3.12"
az webapp config set -g lifeops-rg -n <APP_NAME> --startup-file "python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"

# MySQL Flexible Server (takes several minutes; wait for it to finish)
az mysql flexible-server create -g lifeops-rg -n <MYSQL_NAME> -l eastus \
  --tier Burstable --sku-name Standard_B1ms --storage-size 20 --version 8.0.21 \
  --admin-user lifeopsadmin --admin-password '<NEW_STRONG_PASSWORD>' --public-access 0.0.0.0
az mysql flexible-server db create -g lifeops-rg -s <MYSQL_NAME> -d lifeops --charset utf8mb4 --collation utf8mb4_0900_ai_ci
```

`--public-access 0.0.0.0` creates the "allow Azure services" firewall rule the web app needs. Add a rule for your own IP only if you need to connect from your machine; some networks block TCP 3306 anyway, and the public IP changes over time.

## 2. App settings

Set them with `az webapp config appsettings set -g lifeops-rg -n <APP_NAME> --settings KEY=value ...`. Take the watsonx values from the local `.env`; never commit them.

| Setting | Value |
|---|---|
| `DB_HOST` | `<MYSQL_NAME>.mysql.database.azure.com` |
| `DB_PORT` | `3306` |
| `DB_NAME` | `lifeops` |
| `DB_USER` | `lifeopsadmin` |
| `DB_PASSWORD` | the new admin password |
| `DB_SSL_CA` | `/etc/ssl/certs/ca-certificates.crt` |
| `AI_PROVIDER` | `watsonx` |
| `WATSONX_API_KEY`, `WATSONX_PROJECT_ID` | from the local `.env` |
| `WATSONX_URL` | `https://au-syd.ml.cloud.ibm.com` |
| `WATSONX_MODEL_ID` | `meta-llama/llama-3-3-70b-instruct` |
| `TZ` | `America/Sao_Paulo` |
| `PYTHONPATH` | `/home/site/wwwroot/.python_packages/lib/site-packages` |
| `SCM_DO_BUILD_DURING_DEPLOYMENT` | `false` |
| `WEBSITE_RUN_FROM_PACKAGE` | `1` |
| `WEBSITES_PORT` | `8000` |
| `WEBSITES_CONTAINER_START_TIME_LIMIT` | `600` |
| `REQUIRE_SESSION` | `true` |
| `AI_DAILY_CAP` | `150` |
| `MAX_TASKS_PER_VISITOR` | `30` |
| `MAX_BLOCKS_PER_VISITOR` | `30` |

## 2b. Build the deployment package

`ibm-cos-sdk` (a dependency of `ibm-watsonx-ai`) has no Windows wheels, so build the dependencies in a Linux container and zip everything with forward-slash paths (zips made by the Windows tools break on Linux). Docker Desktop must be running.

```bash
# from the repository root; creates ./pkg with dependencies and the app
docker run --rm -v "$PWD/backend:/src:ro" -v "$PWD/pkg:/out" python:3.12-slim bash -c \
  "pip install --no-cache-dir --target /out/.python_packages/lib/site-packages -r /src/requirements.txt && cp -r /src/app /out/app"
```

Zip the contents of `pkg` (not the folder itself) with Python's `zipfile`, writing names with `/`. A previous build of this package (`lifeops-api-v4.zip`, about 52 MB, no secrets inside) was kept in `C:\Users\Gabriel\Backups\lifeops` and can be reused if the backend code has not changed.

## 3. Deploy and verify

```bash
az webapp deploy -g lifeops-rg -n <APP_NAME> --src-path lifeops-api.zip --type zip
```

The command can print a non-zero exit code even when the deployment worked, so verify by polling:

```bash
curl -s https://<APP_NAME>.azurewebsites.net/health
```

The first start is slow (up to about 20 s, longer right after a deploy). Then check an API route with a session header and a session-less request:

```bash
curl -s -H "X-Session-Id: redeploy-check-0000000000" https://<APP_NAME>.azurewebsites.net/api/v1/tasks/   # 200 []
curl -s https://<APP_NAME>.azurewebsites.net/api/v1/tasks/                                                  # 400 session id required
```

Delete any test data you create.

## 4. Point the frontend at the new API

1. Edit `frontend/vercel.json`: change the `destination` host to `https://<APP_NAME>.azurewebsites.net/api/$1`.
2. Commit and push; Vercel redeploys automatically. Keep the rewrite as `/api/(.*)` (a stricter pattern returned 404 for URLs with a trailing slash).
3. Test the whole flow on the public site, including a real recommendation in Portuguese and English.
4. Update the Better Stack monitor URL, and the "Deployment State" section of `agents.md`.

## Lessons from the first deployment

- **Cost:** only the MySQL server costs money (the F1 plan and web app are free). Delete the resource group (`az group delete -n lifeops-rg --yes`) when the demo is over. Stopping the MySQL server only pauses compute, still bills storage, and Azure starts it again by itself after 7 days.
- **Quota and regions:** F1 had zero quota in East US, so the plan is in South Central US while the database is in East US.
- **Subscription state:** `az account show` can show a stale "Disabled" state; use `az account list --refresh`.
- **Timing:** MySQL creation takes several minutes; wait for it instead of interrupting.
- **Abuse protection:** keep `REQUIRE_SESSION`, `AI_DAILY_CAP` and the per-visitor limits; without them the shared default user and the watsonx quota are exposed.
- **Pinning:** `backend/requirements.txt` is pinned to the validated versions.
