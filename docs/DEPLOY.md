# Deploying the API to Google Cloud Run

This guide puts the FastAPI backend (`api/main.py`) on Google Cloud Run and
connects the live Streamlit app to it (PLAN.md, M4). It takes about 20 minutes
the first time; later deploys are one command.

**What you end up with:** the API runs in a container on Cloud Run, starts
when a request arrives and scales to zero when idle (no cost while idle). The
Streamlit app sends demo questions to it over HTTPS with a bearer token.
Uploaded PDFs stay in the Streamlit app (decision D3).

**Cost:** expected $0/month for compute at demo traffic (Cloud Run's free tier
covers 2 million requests a month plus CPU and memory time; see the
[pricing page](https://cloud.google.com/run/pricing)). Container images are
stored in Artifact Registry, which is free up to 0.5 GB; this image is
larger, so storage costs roughly $0.10 per GB per month
([pricing](https://cloud.google.com/artifact-registry/pricing)). Gemini calls
use the Gemini key's own free quota. Cloud Run needs a billing account.

Commands below are for Git Bash on Windows (they also work on macOS/Linux).
Replace `YOUR_PROJECT_ID` with your project's ID.

---

## 0. One-time prerequisites

1. **Project:** in the [Cloud console](https://console.cloud.google.com),
   pick or create a project and note its **project ID**.
2. **Billing:** Billing -> link a billing account to the project.
3. **Budget alert:** Billing -> Budgets & alerts -> Create budget, e.g.
   $5/month with email alerts at 50% and 100%. Note: a budget only
   **alerts**, it does not stop spending. The safety nets that do limit cost
   are in the deploy command: at most 1 instance, 0 when idle.
4. **gcloud CLI:** install the Google Cloud CLI, open a new terminal and run:

   ```bash
   gcloud auth login
   gcloud config set project YOUR_PROJECT_ID
   ```

## 1. Enable the services

```bash
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com secretmanager.googleapis.com
```

## 2. Store the two secrets in Secret Manager

The Gemini key and an access token for the API live in Secret Manager; they
are never in the code, the image or the repo.

**Gemini API key.** This command reads the key without echoing it or saving
it in your shell history. Paste the key, press Enter:

```bash
read -rs KEY && printf '%s' "$KEY" | gcloud secrets create gemini-api-key --data-file=- && unset KEY
```

Use the key whose quota the live demo should use (the one the Streamlit app
uses today), not the CI key.

**API access token.** A random password the Streamlit app sends with each
request, so only your app can spend your quota through the API:

```bash
TOKEN=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
printf '%s' "$TOKEN" | gcloud secrets create insurance-rag-api-token --data-file=-
unset TOKEN
```

You'll need this token again in step 6; you can always read it back with
`gcloud secrets versions access latest --secret=insurance-rag-api-token`.

## 3. Grant the permissions Cloud Run needs

Cloud Run builds and runs the service as the project's default compute
service account. It needs to read the two secrets and to build from source:

```bash
PROJECT_NUMBER=$(gcloud projects describe YOUR_PROJECT_ID --format='value(projectNumber)')
SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

for SECRET in gemini-api-key insurance-rag-api-token; do
  gcloud secrets add-iam-policy-binding "$SECRET" \
    --member="serviceAccount:$SA" --role=roles/secretmanager.secretAccessor
done

gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:$SA" --role=roles/run.builder
```

## 4. Deploy

From the repository root:

```bash
make deploy PROJECT=YOUR_PROJECT_ID
```

which runs:

```bash
gcloud run deploy insurance-rag-api --source . --project YOUR_PROJECT_ID --region us-central1 \
  --allow-unauthenticated --min-instances 0 --max-instances 1 --memory 1Gi --cpu 1 --timeout 120 \
  --update-secrets=GEMINI_API_KEY=gemini-api-key:latest,INSURANCE_RAG_API_TOKEN=insurance-rag-api-token:latest
```

- `--source .` uploads the repo (minus what `.gcloudignore` excludes); Cloud
  Build builds the `Dockerfile` and stores the image in an Artifact Registry
  repository called `cloud-run-source-deploy`. The first time, gcloud asks to
  create that repository: answer **Y**.
- `--allow-unauthenticated` makes the URL reachable from the internet; the
  API itself still requires the bearer token for `/ask` (only `/health` is
  open).
- `--min-instances 0 --max-instances 1`: nothing runs while idle, and at most
  one instance ever runs, which caps cost and keeps the API's in-memory rate
  limits meaningful.

The first deploy takes 5-10 minutes. At the end it prints the **Service URL**
(`https://insurance-rag-api-....run.app`).

## 5. Check it

```bash
URL=https://YOUR-SERVICE-URL
curl "$URL/health"
```

Expect `"status": "ok"`, `"index_loaded": true`, `"api_key_present": true`,
`"auth_required": true`. Then one real question (1 Gemini call):

```bash
TOKEN=$(gcloud secrets versions access latest --secret=insurance-rag-api-token)
curl -X POST "$URL/ask" -H "Authorization: Bearer $TOKEN" \
  -H "content-type: application/json" -d '{"question": "Is physiotherapy covered under paramedical services?"}'
unset TOKEN
```

Without the token, `/ask` returns 401: that's the guard working.

## 6. Connect the live Streamlit app

On [share.streamlit.io](https://share.streamlit.io), open the app's
**Settings -> Secrets** and add (keep the existing `GEMINI_API_KEY`, which
upload mode still uses):

```toml
INSURANCE_RAG_API_URL = "https://YOUR-SERVICE-URL"
INSURANCE_RAG_API_TOKEN = "the token from step 2"
```

Save; the app restarts. The demo page now shows "Demo served by API: ..." and
demo questions are answered by Cloud Run. The first question after a quiet
period takes a few extra seconds while the service wakes up.

---

## Later

- **Redeploy after changes:** merge to `master`, pull, run `make deploy
  PROJECT=YOUR_PROJECT_ID` again. CI's `docker` workflow has already built and
  started the image, so a broken container is caught before this step.
- **Rotate a secret:** add a new version (`printf '%s' "$NEW" | gcloud secrets
  versions add gemini-api-key --data-file=-`), then redeploy so new instances
  start with it. Secrets used as environment variables are read when an
  instance starts.
- **Logs:** Cloud console -> Cloud Run -> `insurance-rag-api` -> Logs. Each
  response carries an `X-Request-ID` header to find its log lines.
- **Old images:** every deploy adds an image to `cloud-run-source-deploy`.
  Delete old ones now and then (Artifact Registry in the console) to stay near
  the free storage amount.
- **Stop everything:** `gcloud run services delete insurance-rag-api --region
  us-central1`, and remove the two secrets in the Streamlit app.

## Troubleshooting

- **Build fails with a permission error:** re-run the `roles/run.builder`
  grant in step 3; new projects can take a minute for grants to apply.
- **"Failed to start" / container exits:** open the service's Logs. A missing
  secret binding (step 3) stops the instance from starting.
- **`--allow-unauthenticated` refused:** an organization policy can block
  public access (not usual for personal accounts). Deploy without that flag,
  then run `gcloud run services update insurance-rag-api --region us-central1
  --no-invoker-iam-check`.
- **`/ask` returns 503 "quota is used up":** the Gemini key's free tier
  allows 20 generation requests per day per project and model, shared with
  anything else using that key. It resets at midnight Pacific; the message
  says when.
- **`/ask` returns 503 "temporarily unavailable":** Gemini didn't respond
  (the container gives each call 20 s and one retry, so this comes back in
  under a minute instead of hitting Cloud Run's 120 s limit). The service's
  Logs show one `ask failed ... error=... cause=...` line per failed
  question; `cause=APITimeoutError` means Gemini was too slow, a
  `RateLimitError` means a rate limit.
- **"upstream request timeout" after 2 minutes:** Cloud Run cut the request
  off. With the current image this shouldn't happen; redeploy (`make deploy`)
  if the service still runs an older image.
- **The app says the answer service isn't reachable:** check the URL in the
  Streamlit secrets (no trailing path) and that `curl "$URL/health"` works.
- **The app says it isn't authorized:** the token in the Streamlit secrets
  doesn't match the `insurance-rag-api-token` secret.
