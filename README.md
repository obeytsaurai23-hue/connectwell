# Connectwell — Blueprint

Connectwell is a mobile-first, anonymous-first random video/text chat platform with a simple Email+PIN verification flow, microtransactions (coins), subscriptions (Premium), ad monetization and AI-based safety/moderation.

Core goals
- Anonymous quick-mode (anon token) for instant entry
- Verified mode via Email + 4-digit PIN to enable payments and reputation
- Monetized via low-cost coin packs, subscription ($4.99/mo), and ad revenue
- Safety via automatic NSFW detection and blurred video by default
- Mobile-first, low-latency using WebRTC and Django Channels

Tech stack (initial)
- Backend: Python 3.11+, Django, Django REST Framework
- Realtime: Django Channels, Channels Redis
- DB: PostgreSQL
- Cache/queues: Redis
- WebRTC for media, coturn for TURN
- AI/Moderation: Python (PyTorch/TensorFlow), scikit-learn
- Payments: Yoco (USD)
- Frontend: HTML5, CSS3, Vanilla JS (mobile-first)
- Containerization: Docker / docker-compose

Getting started (local dev)
1. Install Python 3.11+ and Docker.
2. Copy `.env.example` -> `.env` and fill DB/Redis credentials.
3. Start services:

   # Example (PowerShell)
   docker compose up --build -d

4. Create virtualenv and install backend deps (optional, if not using container):

   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt

What's included in this repo (blueprint)
- `docs/` — architecture, API spec, payment integration notes
- `frontend/` — simple landing page and login sketch (mobile-first)
- `backend/` — starter Django models sketch
- `docker-compose.yml` — local dev services (postgres, redis, web, coturn placeholder)
- `coins_config.json` — coin packs and costs

Next steps
- Review the docs and approve flow and pricing.
- I can scaffold a runnable Django project with the auth API (send PIN, verify PIN), simple wallet endpoints, and a Channels consumer for matchmaking. Ask me to proceed and I will implement the backend skeleton and run quick tests.

## Deployment (staging / production)

This repository includes basic Docker support to run a staging environment with Postgres and Redis.

Quick local staging (requires Docker & Docker Compose):

```pwsh
# Copy and edit .env from .env.example
cp .env.example .env
# (edit .env and set DJANGO_SECRET_KEY, YOCO_WEBHOOK_SECRET, etc.)
docker compose -f docker-compose.prod.yml up --build
```

Notes:
- The `backend/Dockerfile` starts Daphne on port 8000. In production you should run migrations and collectstatic during your deploy pipeline before starting the web service.
- Replace passwords and secrets before deploying. Use a secrets manager for sensitive values.
- For WebRTC in restrictive NATs, provision a TURN server (coturn) and add its credentials to the frontend configuration.

### Database migration & backups

Plan and checklist to move from the local SQLite dev DB to Postgres in staging/production:

1. Prepare Postgres instance (managed Postgres, RDS, Cloud SQL, or self-hosted). Create a DB user and database.
2. Add the `DATABASE_URL` env variable to your `.env` (example in `.env.example`). The format is:

    postgres://username:password@hostname:5432/dbname

3. Run migrations against Postgres locally (or in CI) before switching traffic:

```pwsh
cd backend
# ensure DATABASE_URL is set in env or .env
python manage.py migrate --noinput
```

4. Backups

- Use the provided scripts in `scripts/pg_backup.sh` and `scripts/pg_restore.sh` for Linux/containers. Example:

```bash
# backup (writes to /backups by default)
PGHOST=postgres PGPORT=5432 PGUSER=postgres PGPASSWORD=secret PGDATABASE=connectwell \ \
   ./scripts/pg_backup.sh /path/to/store/backups

# restore
PGHOST=postgres PGPORT=5432 PGUSER=postgres PGPASSWORD=secret PGDATABASE=connectwell \ \
   ./scripts/pg_restore.sh /path/to/store/backups/connectwell_20250101T120000Z.sql.gz
```

- For Windows admins there is `scripts/pg_backup.ps1` (PowerShell) which similarly uses `pg_dump`.

CronJob S3 upload (Secrets)
---------------------------

The provided CronJob can optionally upload backups to S3. To do this securely from Kubernetes you should create a Secret containing AWS credentials and set the `S3_BUCKET` and `S3_REGION` values in the CronJob or Helm chart.

Example Kubernetes Secret (do NOT store secrets in git):

```yaml
apiVersion: v1
kind: Secret
metadata:
   name: connectwell-backup-s3
type: Opaque
stringData:
   AWS_ACCESS_KEY_ID: "<your-access-key>"
   AWS_SECRET_ACCESS_KEY: "<your-secret>"
   AWS_REGION: "us-east-1"
```

If you are using the Helm chart, set `backup.s3.enabled=true`, `backup.s3.bucket=<your-bucket>`, `backup.s3.region=<your-region>` and `backup.s3.secretName=connectwell-backup-s3` (or whatever name you choose). The chart will mount the Secret as environment variables in the backup job so the upload can proceed.

When testing locally or in CI the CronJob will skip the upload if credentials are not present.

5. CI considerations

- The GitHub Actions CI uses a temporary Postgres service for tests. Ensure migrations run there too (the CI workflow already runs tests/migrations).

6. Rollback plan

- Keep automated backups (daily/hourly) and retain a minimum number of snapshots (see `scripts/pg_backup.sh` rotation param).
- Test restore process in a staging environment before any production cutover.

If you'd like, I can:
- scaffold a `cron` job or Kubernetes CronJob for automated backups, encrypt backups and upload to S3, or
- add a managed backup example for AWS RDS/GCP Cloud SQL — tell me which provider you prefer and I will implement the automation.

### Process management & ASGI server

For production deployments you'll want a process supervisor to run the ASGI server (Daphne or Uvicorn) and ensure restarts on failure. Example approaches:

- Containerized: use the provided `Dockerfile` and run the container in your orchestrator (Docker Compose, Kubernetes, ECS). The `entrypoint.sh` runs migrations and collectstatic.
- VM/systemd: use the sample systemd unit at `scripts/systemd/connectwell.service`. Place an env file at `/etc/connectwell.env` with your environment variables and adjust `ExecStart` to point to your virtualenv/daphne binary and `WorkingDirectory`.

Example `systemd` unit (see `scripts/systemd/connectwell.service`):

```
[Unit]
Description=Connectwell Django ASGI application
After=network.target

[Service]
Type=simple
User=www-data
Group=www-data
EnvironmentFile=/etc/connectwell.env
WorkingDirectory=/srv/connectwell/backend
ExecStart=/srv/connectwell/.venv/bin/daphne -b 0.0.0.0 -p 8000 connectwell.asgi:application
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Health checks

Use the `/healthz` endpoint (added to the app) for liveness/readiness probes. For example, an nginx or Kubernetes probe can hit `http://127.0.0.1:8000/healthz` and expect HTTP 200.

### Kubernetes (example manifests)

I scaffolded minimal Kubernetes manifests under the `k8s/` directory to run Connectwell in a cluster:

- `k8s/deployment.yaml` - Deployment for the web app with readiness & liveness probes (uses `/healthz`).
- `k8s/service.yaml` - ClusterIP service to expose the app inside the cluster.
- `k8s/ingress.yaml` - Example Ingress (NGINX) routing host `example.com` to the service.
- `k8s/secret-example.yaml` - Template for required secrets (do NOT store real secrets in git).
- `k8s/configmap-example.yaml` - Template for non-secret configuration (TURN URL, allowed hosts).
- `k8s/cronjob-backup.yaml` - CronJob example that runs a daily Postgres backup and writes to a PVC (or extend to upload to S3).

Deploy notes:

1. Create Secrets/ConfigMap from the example files, replacing placeholder values with secure ones, or use your cloud provider's secret manager and inject via the platform.
2. Build and push your Docker image to a registry, then update the `image:` field in `k8s/deployment.yaml` (or set the `REGISTRY` environment during infra templating).
3. Apply manifests:

```bash
# create namespace (optional)
kubectl create namespace connectwell
kubectl apply -f k8s/secret-example.yaml -n connectwell
kubectl apply -f k8s/configmap-example.yaml -n connectwell
kubectl apply -f k8s/deployment.yaml -n connectwell
kubectl apply -f k8s/service.yaml -n connectwell
kubectl apply -f k8s/ingress.yaml -n connectwell
kubectl apply -f k8s/cronjob-backup.yaml -n connectwell
```

4. Verify pods and health checks:

```bash
kubectl get pods -n connectwell
kubectl get jobs -n connectwell
kubectl logs deploy/connectwell-web -n connectwell
```

If you'd like, I can also template these manifests for Helm or Kustomize, or add an S3-upload step to the CronJob (requires S3 credentials). Tell me which you prefer and I'll implement it.

## Releases & CI publishing

This repository includes CI jobs that build images, run security scans, package the Helm chart and publish release artifacts. The following documents the expected tag-based release flow, required secrets, and how to trigger or test the pipeline locally.

- Tag-based release flow (GitHub Actions):
   - Push a lightweight tag (semantic version, e.g. `v1.2.0`). The `create-release` job will:
      - Build and run the test suite.
      - Package `charts/connectwell` into a chart artifact and upload it to the release assets.
      - Optionally push the Helm chart to the gh-pages branch (if configured) and to an OCI registry when `OCI_REGISTRY` secrets are available.
      - Build and push the `images/backup-job` image when registry credentials are provided.

   Release publishing workflow
   --------------------------

   This repository contains a GitHub Actions workflow (`.github/workflows/release-publish.yml`) that runs when you push a tag matching `v*` (for example `v1.2.0`). The workflow will:

   - Package `charts/connectwell` into a chart archive and upload it as a Release asset.
   - Optionally publish the packaged chart to the `gh-pages` branch when `GH_PAGES_PUSH_TOKEN` is configured.
   - Optionally push the chart to an OCI registry when `OCI_REGISTRY`, `OCI_USERNAME`, `OCI_PASSWORD` and `OCI_REPOSITORY` are configured.
   - Optionally build & push the `images/backup-job` image when `REGISTRY_USERNAME` and `REGISTRY_PASSWORD` are provided.

   Required and optional secrets
   ----------------------------

   At minimum the workflow needs `GITHUB_TOKEN` (automatically provided by GitHub Actions) to create a Release. The following repository secrets are used to enable optional publishing steps: 

   - `GH_PAGES_PUSH_TOKEN` (optional): a token with push permission used by the gh-pages publish step. If present, the packaged chart is committed to `gh-pages`.
   - `OCI_REGISTRY` / `OCI_REPOSITORY` / `OCI_USERNAME` / `OCI_PASSWORD` (optional): used to login and `helm push` the chart into an OCI registry. `OCI_REGISTRY` is the host (for example `ghcr.io`), `OCI_REPOSITORY` is the repo path under the registry.
   - `REGISTRY_USERNAME` / `REGISTRY_PASSWORD` (optional): used by the backup image push step. `REGISTRY_HOST` and `REGISTRY_NAMESPACE` may also be set to control destination.

   How to trigger a release locally
   --------------------------------

   1. Create a lightweight Git tag and push it to the repository:

   ```pwsh
   # create tag and push
   git tag v1.0.0
   git push origin v1.0.0
   ```

   2. After the tag is pushed, GitHub Actions will run the `release-publish` workflow. Check the workflow run logs for packaging and optional publishing steps.

   If you want me to wire these secrets into the repo (you'll need to provide values), I can also prepare a secure checklist and, if desired, run a one-shot publish in CI. Tell me which secrets you can provide and I'll proceed to the next step.

- Required secrets for publishing (set in GitHub repository settings -> Secrets):
   - `DOCKERHUB_USERNAME` / `DOCKERHUB_TOKEN` OR `REGISTRY_USERNAME` / `REGISTRY_PASSWORD` — credentials to push container images.
   - `OCI_REGISTRY` / `OCI_USERNAME` / `OCI_PASSWORD` — optional, for pushing Helm charts to an OCI registry.
   - `GH_PAGES_PUSH_TOKEN` — optional, token with repo write access used by the chart publish job to update gh-pages (if enabled).
   - `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `S3_BUCKET` — optional, used by backup CI jobs to test uploading backups to S3.
   - `SLACK_WEBHOOK_URL` — optional, used by scheduled security scans to post failures.

- Local testing & CI emulation tips:
   - Run the Django unit tests locally from the `backend/` directory:

      ```pwsh
      cd backend
      .\.venv\Scripts\Activate.ps1  # if using venv
      python manage.py migrate --noinput
      python manage.py test --verbosity=2
      ```

   - To verify the Helm chart locally:
      - Install Helm 3 and run `helm lint charts/connectwell` and `helm template charts/connectwell --values charts/connectwell/values.yaml`.

   - The CI uses Trivy and pip-audit to scan images and Python dependencies. You can run `pip-audit` locally in your venv and install Trivy to scan any built image before pushing.

- Notes and caveats:
   - Several CI publishing steps are gated by repository secrets. If the publishing jobs fail due to missing credentials, they will be skipped or fail with a clear message in the workflow logs.
   - The Helm chart packaging/publishing and OCI push steps are idempotent and safe to re-run for patch releases, but follow semantic versioning for clarity.

If you'd like, I can wire up repository secrets (you must provide tokens/credentials), or I can add a GitHub Actions workflow that runs a full end-to-end staging deploy into a test cluster (kind) and executes Playwright E2E tests. Tell me which you'd prefer next.

