# Deploy a pre-built image

Deploy versioned images from GitHub Container Registry without building on the
deployment host. For local builds, use the root Compose file on its own.

## Publish a release

The GitHub Actions workflow tests the frontend and backend, builds the production
container, and smoke-tests its read-only, non-root Compose runtime. Pushes to
`main` and pull requests run these checks without publishing. Pushing a tag such
as `v0.1.0` additionally publishes:

```
ghcr.io/levinuss/keycafe-tableau:0.1.0
```

Images support `linux/amd64` and `linux/arm64`. Only full stable versions
`vMAJOR.MINOR.PATCH` are accepted; no moving `latest`, major, or minor aliases are
published. Choose a new unused version for every release and never move release
tags. Registry tags can still be overwritten by an administrator; for immutable
pinning use `ghcr.io/levinuss/keycafe-tableau@sha256:…` with the manifest digest
from the successful publish step.

After committing and pushing the prepared changes, publish the desired version:

```sh
git tag v0.1.0
git push origin v0.1.0
```

Wait for the **Test and publish container** workflow to succeed before deploying.
Publishing uses the repository's `GITHUB_TOKEN` with `packages: write`; no extra
CI registry secret is needed. GitHub Actions must be enabled and allowed to write
packages. If a package with this name already exists, grant this repository
Actions access to it in the package settings.

GHCR packages are initially private. Either make the package public for anonymous
pulls, or authenticate on the deployment host using a GitHub personal access
token (classic) with `read:packages` and package access:

```sh
# Supply the token through stdin from your secret manager.
printf '%s' "$GHCR_TOKEN" | docker login ghcr.io -u YOUR_GITHUB_USERNAME --password-stdin
```

See GitHub's [container registry documentation](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry).

## Prepare the host

Install Docker Engine and Docker Compose **2.24.4 or newer** (the deployment
override uses `!reset` to remove the local build). Copy only `compose.yaml`,
`compose.deploy.yaml`, and `.env.example` into the deployment directory. No source
checkout, Node, Python, or build tools are needed on the host.

Create `.env` from the example and restrict it with `chmod 600 .env`. Configure:

- `TABLEAU_IMAGE=ghcr.io/levinuss/keycafe-tableau:0.1.0` (a successfully published version).
- A generated `DJANGO_SECRET_KEY`, using the command in `.env.example`.
- `DJANGO_ALLOWED_HOSTS=tableau.example.org,localhost,127.0.0.1`.
- `DJANGO_CSRF_TRUSTED_ORIGINS=https://tableau.example.org`.
- Keycafe credentials and `KEYCAFE_AUTH_MODE`; set `KEYCAFE_DEMO_MODE=false` for live data.
- Optionally `TABLEAU_PORT` for the loopback port (default `8000`).

Replace the example hostname with the new host's public hostname. Protect the
entire origin at your HTTPS reverse proxy, including `/api/` and static files.
The app has no user authentication. Preserve the public Host header and proxy to
`127.0.0.1:8000` (or your chosen port). See the root README for containerized proxies.

```sh
docker compose -p keycafe-tableau -f compose.yaml -f compose.deploy.yaml config --quiet
docker compose -p keycafe-tableau -f compose.yaml -f compose.deploy.yaml pull
docker compose -p keycafe-tableau -f compose.yaml -f compose.deploy.yaml up -d --no-build --wait
docker compose -p keycafe-tableau -f compose.yaml -f compose.deploy.yaml ps
```

Always include both files. The override removes the build and requires an image
reference, so a deployment cannot silently build local source. The health check
verifies the app process, not Keycafe credentials or the reverse proxy. Verify
unauthenticated page/API access is blocked by the proxy, then verify authenticated
asset loading, group editing, and live key status.

## Update or roll back

Back up the named `keycafe-tableau_tableau-data` volume (groups and upstream cache)
and retain the previous image reference before updating. Keep the same deployment
directory, project name and `.env`; never use `down -v` on the deployment host.

Set `TABLEAU_IMAGE` in `.env` to the new published version, then repeat `pull` and
`up -d --no-build --wait` above. To roll back, restore the previous image reference
and repeat those commands. This preserves the volume; future incompatible data
format changes may require restoring its matching backup as well.

Environment changes require container recreation; `up` normally detects these.
Use `up -d --no-build --force-recreate --wait` if explicitly recreating it. A plain
container restart retains its old environment.
