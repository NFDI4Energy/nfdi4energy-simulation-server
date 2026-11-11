# Deploy on a New Machine

For a local Linux setup. Install **Docker, Minikube, kubectl, Git, Python 3,
OpenSSL, curl, and tar** first. Docker must work without `sudo`. Node.js 22/npm is
only needed to run the frontend outside Docker (`npm run build` in `frontend/`
writes `fastapi_app/static/svelte-dist/`, which is not tracked in Git).
The build script reuses Helm if available, otherwise it installs Helm 3 into your
user cache with checksum verification, without `sudo`.

## 1. Switch the Existing Checkout

Open a terminal in the repository. Check `git status --short` and preserve local
changes before switching branches. Do not commit credentials.

```bash
git fetch origin
git switch daceds+mosaik
git pull --ff-only origin daceds+mosaik
git submodule update --init --recursive
```

If the branch exists only on `origin`, `git switch` normally creates a local
tracking branch. The maintainer must publish the complete integration first.
If switching or pulling fails, stop and resolve it without a hard reset.
Keep all subsequent commands in this repository directory.

## 2. Add Credentials

The build script reads only the repository's `.env`, not a parent-directory file.
Keep an existing `.env`; create it from the example only if missing:

```bash
if [ ! -f .env ]; then cp .env.example .env; fi
chmod 600 .env
openssl rand -hex 32
```

Edit `.env` locally:

- `AUTH_DISABLED=true`: local login without OIDC, using a shared development account.
- `SIM_SERVER_HOST=localhost` and `SIM_SERVER_URL=https://localhost:5001` for the
  local Ingress forward below. For separate users, use your deployment hostname
  and HTTPS origin, set `AUTH_DISABLED=false`, and register that origin's
  `/auth/callback` URL with the OIDC provider.
- `OIDC_CLIENT_ID` and `OIDC_CLIENT_SECRET`: may be blank in local mode
- `DB_PASSWORD`: choose a local database password.
- `SESSION_SECRET`: use the generated random value.

Quote shell-special characters. Never commit `.env`. On an existing machine,
keep the existing file and database password. OIDC is enabled by default; use the
local-login bypass only on a trusted local machine, never a public deployment.

## 3. Create Local Certificates

Certificates belong in `certs/`, outside the shared `data/` directory. The build
script migrates an existing `data/certs/{key,cert}.pem` pair there; conflicting
copies must be resolved before deployment. Existing pods must be restarted after
migration because a previous mount may retain access to an open file.

```bash
mkdir -p certs
openssl req -x509 -newkey rsa:2048 -nodes -days 365 \
  -keyout certs/key.pem -out certs/cert.pem \
  -subj "/CN=localhost" \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"
chmod 600 certs/key.pem
```

## 4. Start Minikube and Mount Data

The resource allocation below is a starting point; your host needs spare memory
and tens of GiB of free Docker storage.

```bash
minikube start --driver=docker --container-runtime=docker --cpus=4 --memory=12288 --dns-domain=cluster.local
kubectl config use-context minikube
minikube mount "$(pwd)/data:/data"
```

**Leave this terminal running.** Uploads and results use the mounted `data/`
directory. PostgreSQL and Redis use separate cluster volumes.

## 5. Build and Deploy

In a second terminal:

```bash
bash build-minikube.sh
```

This builds the web image (which compiles the dashboard in a Node build stage),
the DaceDSX worker, the wrappers, and the Mosaik worker. The Mosaik editor and
Orbit use prebuilt registry images. The first SUMO build can take a long time.

The script installs Traefik, creates the Ingress TLS Secret, and generates separate
broker credentials in `.broker-secrets.env` (ignored by Git). Keep this file and
`certs/kafka/` across updates; deleting them changes broker credentials or trust.
It waits for the Traefik Deployment; an external LoadBalancer IP is not required
when using the local port-forward below.
Back up PostgreSQL and finish running tasks before the first secured rollout.
RabbitMQ has no persistent volume in this stack, so its queued requests do not
survive a pod replacement. Existing Redis data is retained while ACLs are enabled.

Kafka uses SASL over TLS with separate application, observer, registry, and admin
roles. RabbitMQ and Redis accept credentials from Kubernetes Secrets. The unused
Kafka REST, Connect, and ksql deployments are scaled to zero because their HTTP
interfaces do not have authentication configured. NetworkPolicies are a separate
deployment phase; these changes do not yet restrict all pod-to-pod traffic.

Check startup before opening the app:

```bash
kubectl -n simservice get pods,jobs
kubectl -n kafka get pods
kubectl -n simservice rollout status deployment/web --timeout=300s
kubectl -n simservice rollout status deployment/mosaik-gui --timeout=300s
```

Service pods should become Ready and the migration job should complete.

## 6. Open the Apps

Run this command in a terminal and leave it running:

```bash
kubectl -n ingress-system port-forward service/simaas-ingress 5001:5001 8002:8002
```

- **Main app:** https://localhost:5001
- **Mosaik editor:** https://localhost:8002/mosaik/ (requires the same login)

Expect a browser warning for the self-signed certificate. Sign in and choose a
framework. Keep access local; do not expose these forwards publicly.

Use **Create scenario** to open the editor through the web application's
authenticated HTTP and WebSocket proxy. Do not publish or port-forward the
internal `mosaik-gui` or `mosaik-orbit` services. Stop any old direct editor
port-forward on port 8002 before starting the gateway forward above; applying
the manifest does not terminate a running port-forward.
Remove old direct web/broker forwards too. The application Services now use
ClusterIP; only the Ingress controller exposes the HTTPS ports 5001 and 8002.

### Exposed Server

Set these values in the deployment's `.env`, using your actual DNS hostname:

```dotenv
AUTH_DISABLED=false
SIM_SERVER_HOST=simulation.example.org
SIM_SERVER_URL=https://simulation.example.org:5001
```

Provide a TLS certificate covering that hostname and register
`https://simulation.example.org:5001/auth/callback` with the OIDC provider.
For Minikube, run `minikube tunnel`, point DNS at a reachable Ingress address,
and configure the server/router firewall and forwarding for TCP 5001 and 8002.
The tunnel alone does not configure your router or public DNS. Do not expose
internal application or broker Services.

The **Create scenario** link derives the hostname from the browser and opens
port 8002 with the same HTTPS scheme. It still passes through the authenticated
proxy; changing ports does not bypass login. Localhost is only a development
default, not a fixed address built into the frontend.

Test one Pandapower run, one SUMO run, and one known-good Mosaik scenario. Verify
completion and downloads. The maintainers supplied these Save/Load-enabled images;
verify the buttons and scenario execution after deployment:

```text
registry.gitlab.com/mosaik/mosaik-gui/frontend:nfdi4energy-simaas
registry.gitlab.com/mosaik/mosaik-gui/mosaik-orbit:nfdi4energy-simaas
```

The GUI image is named `frontend`; its service remains `mosaik-gui`. The editor's
Orbit has no task-data mount. The worker creates a fresh Orbit pod per task with
only that task's resources (read-only) and results (writable), then confirms pod
termination before reporting completion. DaceDSX wrappers receive the same scoped
mounts plus a private input working copy for tools such as SUMO that generate files.

The secure execution path is Kubernetes. Compose is retained for local service
development; its Mosaik worker profile requires Kubernetes credentials and is not
a standalone replacement for this deployment.

## Later Updates

Keep the mount running and finish active simulations before updating:

```bash
bash build-minikube.sh
```

The full script runs every local image build, reusing Docker's cached layers when
possible, applies the manifest, and restarts deployments. Keep the existing `.env`
and database password. Back up PostgreSQL before migrations, and review cluster
overrides because applying the manifest restores declared settings.

<details>
<summary>If something fails</summary>

- **Missing certificate:** check `certs/` and the `web-tls` Secret.
- **Migration timeout:** PostgreSQL may not be ready yet. Inspect the migration
  job logs, wait for PostgreSQL, then rerun the migration job. Do not delete its PVC.
- **Image pull error:** check registry access and the image reference in pod events.
- **Empty SUMO dependencies:** run `git submodule update --init --recursive`.
- **DNS errors:** the cluster domain must be `cluster.local`, not `8.8.8.8`.
- **Port occupied:** stop your previous port-forward before starting another.

</details>

Fresh-machine deployment and the new upstream images still need runtime
verification. Keep access local: Mosaik scenarios are not sandboxed. Back up both
PostgreSQL and `data/`; the host data directory alone does not preserve ownership.
