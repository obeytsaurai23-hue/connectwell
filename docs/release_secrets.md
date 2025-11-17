# Release & CI secrets — checklist

This document lists the repository secrets and permissions required to enable the optional CI publishing steps (gh-pages, OCI chart push, image push) and the k8s S3 upload for backups. It also includes safe copy/paste snippets for admins to add secrets using the GitHub CLI or via the web UI.

Important: Never store credentials in the Git repository. Use GitHub repository Secrets or your cloud provider's secret manager.

1) GitHub Release and attachments
  - GITHUB_TOKEN: Provided automatically by GitHub Actions. No action required.

2) Publish to gh-pages (optional)
  - Secret name: `GH_PAGES_PUSH_TOKEN`
  - Purpose: used to push packaged chart files into the `gh-pages` branch.
  - Minimum required scopes for a personal access token (PAT): `repo` (or at least `repo:status, repo_deployment, public_repo, repo:invite, repo:write` depending on org policies). Using a machine account with only the required access is recommended.

3) Push chart to OCI registry (optional)
  - Secrets:
    - `OCI_REGISTRY` — e.g. `ghcr.io` or `oci.example.com`
    - `OCI_REPOSITORY` — path inside the registry, e.g. `myorg/connectwell-charts`
    - `OCI_USERNAME` — registry username (or `__token` for GHCR)
    - `OCI_PASSWORD` — registry password or token
  - Minimum scopes: package write/publish for the target registry (for GHCR use `write:packages`), or equivalent for private registries.

4) Push images to container registry (optional)
  - Secrets:
    - `REGISTRY_USERNAME` — e.g. Docker Hub username or registry user
    - `REGISTRY_PASSWORD` — corresponding password or token
    - `REGISTRY_HOST` — optional, default `docker.io` if blank
    - `REGISTRY_NAMESPACE` — optional; will be used as the repository namespace (defaults to repo owner)
  - Minimum scopes: `push` access to the registry/repository namespace. Use short-lived tokens or robot/service accounts when possible.

5) S3 upload from CronJob (k8s)
  - Kubernetes Secret (created in the cluster; not a repo secret)
    - Name: set the value into the Helm chart using `backup.s3.secretName`, e.g. `connectwell-backup-s3`
    - Keys inside the Secret (stringData):
      - `AWS_ACCESS_KEY_ID`
      - `AWS_SECRET_ACCESS_KEY`
      - `AWS_REGION` (optional, default `us-east-1`)
  - The Helm chart will inject the named Secret as env vars into the CronJob when `backup.s3.secretName` is set.

6) Guidance & commands
  - Add repository secret with GitHub CLI (PowerShell):

    ```pwsh
    # Install GitHub CLI and authenticate first: gh auth login
    gh secret set GH_PAGES_PUSH_TOKEN --body "<your-pat-here>"
    gh secret set OCI_REGISTRY --body "ghcr.io"
    gh secret set OCI_REPOSITORY --body "myorg/connectwell-charts"
    gh secret set OCI_USERNAME --body "<username>"
    gh secret set OCI_PASSWORD --body "<token>"
    gh secret set REGISTRY_USERNAME --body "<registry-user>"
    gh secret set REGISTRY_PASSWORD --body "<registry-token>"
    ```

  - For GitHub Container Registry (GHCR) use a PAT with `write:packages` and login user `USERNAME` and token `TOKEN`.
  - For Docker Hub use a robot account and the robot's access token instead of the human password.

7) Minimal checklist to hand to the repo admin
  - [ ] Create a PAT for gh-pages push: add as `GH_PAGES_PUSH_TOKEN`.
  - [ ] Provide OCI registry info and credentials: `OCI_REGISTRY`, `OCI_REPOSITORY`, `OCI_USERNAME`, `OCI_PASSWORD` (if you want OCI publishing).
  - [ ] Provide registry credentials for image push: `REGISTRY_USERNAME`, `REGISTRY_PASSWORD`, optionally `REGISTRY_HOST` and `REGISTRY_NAMESPACE`.
  - [ ] Create a Kubernetes Secret inside your cluster for S3 backups and set `backup.s3.secretName` in Helm values.

8) Security recommendations
  - Use dedicated machine/service accounts with minimal scopes.
  - Rotate tokens periodically and after personnel changes.
  - Prefer short-lived credentials (OIDC federation) where supported by your registry/CI.

If you provide which optional steps you want enabled (gh-pages, OCI, image push), I will prepare a one-shot test plan and, after you set secrets in GitHub, trigger a tag push to run the publishing workflow.
