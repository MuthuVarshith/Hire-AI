# Deploying to Google Cloud Run with Neon PostgreSQL (free tiers)

This guide runs Hire AI on Cloud Run (scales to zero) with a free Neon PostgreSQL database that has pgvector. Nothing here is automated; run each step yourself. Free-tier limits change, so check the Cloud Run, Artifact Registry and Neon pricing pages before you start.

> **Synthetic resumes only with Gemini.** If you set `GOOGLE_API_KEY`, only send sample or synthetic resumes. On Gemini's free tier, content may be used to improve Google's products. Leave the key unset for real candidates' data; the app works fully without it.

## 0. Prerequisites

- A Google Cloud account with billing enabled (Cloud Run requires it even within the free tier).
- The `gcloud` CLI, logged in: `gcloud auth login`.
- Docker, to build the image locally (or use Cloud Build, step 4).

Set these once per shell (bash shown; adjust for PowerShell):

```bash
export PROJECT_ID=hireai-demo-12345      # globally unique
export REGION=us-central1                # a free-tier region
export REPO=hireai
export IMAGE=$REGION-docker.pkg.dev/$PROJECT_ID/$REPO/api:v1
```

## 1. Project and APIs

```bash
gcloud projects create $PROJECT_ID
gcloud config set project $PROJECT_ID
gcloud billing projects link $PROJECT_ID --billing-account=XXXXXX-XXXXXX-XXXXXX
gcloud services enable run.googleapis.com artifactregistry.googleapis.com \
  secretmanager.googleapis.com cloudbuild.googleapis.com billingbudgets.googleapis.com
```

## 2. Budget alert

Set an alert before deploying anything (it notifies; it does not stop spending):

```bash
gcloud billing budgets create \
  --billing-account=XXXXXX-XXXXXX-XXXXXX \
  --display-name="hireai-budget" \
  --budget-amount=5USD \
  --filter-projects=projects/$PROJECT_ID \
  --threshold-rule=percent=0.5 \
  --threshold-rule=percent=0.9 \
  --threshold-rule=percent=1.0
```

## 3. Neon database

1. Sign up at https://neon.tech and create a project (free plan) in a region close to `$REGION`, e.g. AWS us-east.
2. In the Neon SQL editor, run:

   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   ```

   (Migration 0002 also runs `CREATE EXTENSION IF NOT EXISTS vector`; doing it first confirms it is available.)
3. Copy the **direct** (not pooled) connection string and change the scheme for psycopg 3:

   ```
   postgresql+psycopg://USER:PASSWORD@ep-xxxx.us-east-2.aws.neon.tech/neondb?sslmode=require
   ```

   Keep `sslmode=require`. The direct endpoint avoids PgBouncer transaction pooling, which can break Alembic and psycopg prepared statements. Neon's free compute suspends when idle, so the first request after a pause is slower.

## 4. Artifact Registry, build and push

```bash
gcloud artifacts repositories create $REPO --repository-format=docker --location=$REGION
# Keep only the 2 newest images (free storage is about 0.5 GB; the image is ~1.5 GB, so expect cents per month).
cat > cleanup.json <<'EOF'
[{"name":"keep-2","action":{"type":"Keep"},"mostRecentVersions":{"keepCount":2}},
 {"name":"delete-rest","action":{"type":"Delete"},"condition":{"tagState":"any"}}]
EOF
gcloud artifacts repositories set-cleanup-policies $REPO --location=$REGION --policy=cleanup.json --no-dry-run

gcloud auth configure-docker $REGION-docker.pkg.dev
docker build --platform linux/amd64 -t $IMAGE .
docker push $IMAGE
```

Alternative without local Docker: `gcloud builds submit --tag $IMAGE .` (uses Cloud Build minutes).

## 5. Secrets in Secret Manager

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))" | tr -d '\n' | \
  gcloud secrets create hireai-auth-secret --data-file=-
printf '%s' 'postgresql+psycopg://USER:PASSWORD@ep-xxxx.../neondb?sslmode=require' | \
  gcloud secrets create hireai-database-url --data-file=-
# Optional, synthetic data only:
printf '%s' 'YOUR_GEMINI_KEY' | gcloud secrets create hireai-google-api-key --data-file=-

PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')
for s in hireai-database-url hireai-google-api-key; do
  gcloud secrets add-iam-policy-binding $s \
    --member="serviceAccount:$PROJECT_NUMBER-compute@developer.gserviceaccount.com" \
    --role=roles/secretmanager.secretAccessor
done
```

Never put these values in files in the repository or in plain `--set-env-vars`.

## 6. Deploy

```bash
gcloud run deploy hireai \
  --image=$IMAGE \
  --region=$REGION \
  --allow-unauthenticated \
  --port=8080 \
  --memory=2Gi --cpu=1 \
  --min-instances=0 --max-instances=1 \
  --concurrency=20 --timeout=300 \
  --set-secrets=DATABASE_URL=hireai-database-url:latest \
  --set-env-vars=AUTH_TOKEN_TTL_HOURS=12,HF_HUB_OFFLINE=1,FORWARDED_ALLOW_IPS=*,ASK_LLM_ENABLED=false,AGENT_LLM_ENABLED=false
```

- `--allow-unauthenticated` exposes the URL; the app's own login protects every API route.
- 2 GiB covers PyTorch plus all-MiniLM-L6-v2 (baked into the image, loaded offline).
- `--max-instances=1` caps cost, and keeps paused agent runs (a SQLite file per instance) on one instance.
- `FORWARDED_ALLOW_IPS=*` lets uvicorn trust Cloud Run's `X-Forwarded-Proto`, so the session cookie is marked `Secure`.
- To use Gemini (synthetic data only), add `GOOGLE_API_KEY=hireai-google-api-key:latest` to `--set-secrets`.

**Environment variables**

| Variable | Where | Value |
|---|---|---|
| `DATABASE_URL` | Secret Manager | Neon string, `postgresql+psycopg://...?sslmode=require` |
| `GOOGLE_API_KEY` | Secret Manager, optional | synthetic data only |
| `AUTH_TOKEN_TTL_HOURS` | env | `12` |
| `HF_HUB_OFFLINE` | env (also set in the image) | `1` |
| `FORWARDED_ALLOW_IPS` | env | `*` |
| `ASK_LLM_ENABLED`, `AGENT_LLM_ENABLED` | env | `false` unless using synthetic data |
| `PORT` | set by Cloud Run | `8080` |

**Limits.** Cloud Run's filesystem is in memory and is wiped when the instance stops: uploaded resume files (`/app/uploads`) and paused agent runs (`/app/data`) do not survive scale-to-zero. Records, scores and embeddings live in Neon and do. For persistent files, mount a Cloud Storage bucket at `/app/uploads` (`--add-volume=name=uploads,type=cloud-storage,bucket=BUCKET --add-volume-mount=volume=uploads,mount-path=/app/uploads`).

Check it: `curl "$(gcloud run services describe hireai --region=$REGION --format='value(status.url)')/api/health"`.

## 7. First admin

There are no default users. Create the admin once, from your machine against the Neon database (migrations run on connect):

```bash
pip install -r requirements.txt
DATABASE_URL='postgresql+psycopg://USER:PASSWORD@ep-xxxx.../neondb?sslmode=require' \
  python -m app.cli create-admin --username admin
```

It prompts for the password twice (at least 12 characters). Alternatively run it as a Cloud Run job with the same image and secrets, but the prompt needs a terminal, so the local route is simpler.

## 8. Teardown

```bash
gcloud run services delete hireai --region=$REGION
gcloud artifacts repositories delete $REPO --location=$REGION
gcloud secrets delete hireai-database-url
gcloud secrets delete hireai-google-api-key
gcloud billing budgets list --billing-account=XXXXXX-XXXXXX-XXXXXX   # then: gcloud billing budgets delete BUDGET_ID --billing-account=...
gcloud projects delete $PROJECT_ID                                  # removes everything above in one go
```

Then delete the Neon project in the Neon console (Settings, Delete project).
