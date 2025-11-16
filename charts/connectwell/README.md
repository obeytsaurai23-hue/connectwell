# Connectwell Helm Chart

This Helm chart packages the Connectwell Django backend and related Kubernetes resources.

Quick start
-----------
1. Edit `values.yaml` (or provide `--values my-values.yaml`) to set image, database, redis, and secrets.
2. Install the chart:

   helm install my-connectwell ./charts/connectwell -f my-values.yaml

Key values
----------
- `image.repository` / `image.tag`: backend image
- `replicaCount`: number of backend replicas
- `postgres.*`: DB connection details (in production, use a Secret and set `postgres.enabled`)
- `redis.url`: redis URL for channel layer
- `secrets.yoco_webhook_secret`: YOCO webhook secret (sensitive — use Kubernetes Secret or external secret store)
- `backup.*`: enable backup CronJob and S3 upload options

Notes
-----
- This chart is a scaffold and intended to be customized for your infrastructure.
- For production: ensure that secrets are provided via Kubernetes Secret or an external secrets manager, and configure resource requests/limits.
