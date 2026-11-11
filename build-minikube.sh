#!/usr/bin/env bash
#
# Simulation Server: Minikube build and deployment
# =================================================
#
# Prerequisites:
#   minikube start --driver=docker
#   cp .env.example .env
#   chmod 600 .env
# Helm is reused if available; otherwise Helm 3 is downloaded with checksum
# verification to the user's cache directory (requires curl and tar, no sudo).
#
# For local use without OIDC credentials, set AUTH_DISABLED=true in .env.
# Otherwise populate OIDC_CLIENT_ID and OIDC_CLIENT_SECRET (the default mode).
# Choose a local DB_PASSWORD and generate SESSION_SECRET
# with:
#   openssl rand -hex 32
#
# HTTPS certificates
#   certs/key.pem
#   certs/cert.pem
#
# A local self-signed pair can be generated with:
#   mkdir -p certs
#   openssl req -x509 -newkey rsa:2048 -nodes -days 365 \
#     -keyout certs/key.pem -out certs/cert.pem \
#     -subj "/CN=localhost" \
#     -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"
#
# Keep the data mount running in a separate terminal:
#   minikube mount "$(pwd)/data:/data"
#
# Build and deploy:
#   ./build-minikube.sh
#
# Expose the authenticated HTTPS gateway, not the internal editor:
#   kubectl -n ingress-system port-forward service/simaas-ingress 5001:5001 8002:8002
#
# Open:
#   https://localhost:5001
#   https://localhost:8002/mosaik/ (Mosaik editor, requiring the web login)
# For a server, set SIM_SERVER_HOST and SIM_SERVER_URL to its public hostname
# and HTTPS origin (e.g. https://simulation.example.org:5001), and use OIDC.
#
# Inspect the cluster:
#   kubectl -n simservice get pods,jobs
#   kubectl -n kafka get pods
#   kubectl -n simservice logs deployment/web -f
#   kubectl -n simservice logs deployment/simservice -f
#   kubectl -n simservice logs deployment/log-consumer -f
#   kubectl get events -A --sort-by=.lastTimestamp
#
# Set MINIKUBE_PROFILE before running to use a non-default profile.
# Back up existing PostgreSQL before the additive task-framework migration.
# Mosaik starts enabled for trusted local use; simulator code is not sandboxed.
# See docs/deployment-guide.md for setup, verification, and recovery.

set -Eeuo pipefail

readonly ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly PROFILE="${MINIKUBE_PROFILE:-minikube}"
readonly ENV_FILE="${ROOT_DIR}/.env"
readonly MANIFEST="${ROOT_DIR}/simservice/k8s/minikube-full-stack.yaml"
readonly NAMESPACE="simservice"

TEMP_DIR=""

log() {
    printf '\n==> %s\n' "$*"
}

fail() {
    printf 'Error: %s\n' "$*" >&2
    exit 1
}

cleanup() {
    if [[ -n "${TEMP_DIR}" && -d "${TEMP_DIR}" ]]; then
        rm -rf -- "${TEMP_DIR}"
    fi
}

trap cleanup EXIT
trap 'printf "Build failed at line %s.\n" "${LINENO}" >&2' ERR

require_command() {
    command -v "$1" >/dev/null 2>&1 || fail "Required command not found: $1"
}

ensure_helm() {
    if command -v helm >/dev/null 2>&1; then
        return
    fi

    local version="v3.22.1"
    local install_dir="${XDG_CACHE_HOME:-${HOME}/.cache}/simaas/helm-${version}"
    export PATH="${install_dir}:${PATH}"
    if command -v helm >/dev/null 2>&1; then
        return
    fi

    require_command curl
    require_command tar
    mkdir -p "${install_dir}"
    TEMP_DIR="$(mktemp -d)"
    log "Installing Helm ${version} locally (no sudo)"
    curl --fail --silent --show-error --location --retry 3 \
        --connect-timeout 15 --max-time 120 \
        "https://raw.githubusercontent.com/helm/helm/${version}/scripts/get-helm-3" \
        --output "${TEMP_DIR}/install-helm.sh"
    HELM_INSTALL_DIR="${install_dir}" USE_SUDO=false VERIFY_CHECKSUM=true \
        bash "${TEMP_DIR}/install-helm.sh" --version "${version}"
    cleanup
    TEMP_DIR=""
    require_command helm
}

require_value() {
    local name="$1"
    local value="${!name:-}"

    [[ -n "${value}" ]] || fail "${name} is missing from ${ENV_FILE}"
    case "${value}" in
        replace-*|change-me-*|\*\*\*REMOVED*)
            fail "${name} still contains a placeholder value"
            ;;
    esac
}

build_image() {
    local tag="$1"
    local context="$2"
    local dockerfile="${3:-${context}/Dockerfile}"

    log "Building ${tag}"
    docker build --tag "${tag}" --file "${dockerfile}" "${context}"
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    sed -n '2,/^set -Eeuo pipefail$/p' "${BASH_SOURCE[0]}" | sed '$d'
    exit 0
fi

[[ $# -eq 0 ]] || fail "Unknown argument: $1"

for command_name in minikube kubectl docker python3 openssl; do
    require_command "${command_name}"
done
ensure_helm

[[ -f "${ENV_FILE}" ]] || fail "Create ${ENV_FILE} from .env.example and populate it first"
[[ -f "${MANIFEST}" ]] || fail "Kubernetes manifest not found: ${MANIFEST}"
mkdir -p "${ROOT_DIR}/certs"
for name in key.pem cert.pem; do
    if [[ -f "${ROOT_DIR}/data/certs/${name}" ]]; then
        if [[ -f "${ROOT_DIR}/certs/${name}" ]]; then
            cmp -s "${ROOT_DIR}/data/certs/${name}" "${ROOT_DIR}/certs/${name}" || fail "Conflicting TLS files; move data/certs outside shared storage first"
            rm "${ROOT_DIR}/data/certs/${name}"
        else
            mv "${ROOT_DIR}/data/certs/${name}" "${ROOT_DIR}/certs/${name}"
        fi
    fi
done
[[ -f "${ROOT_DIR}/certs/key.pem" ]] || fail "Missing certs/key.pem"
[[ -f "${ROOT_DIR}/certs/cert.pem" ]] || fail "Missing certs/cert.pem"
chmod 600 "${ROOT_DIR}/certs/key.pem"

chmod 600 "${ENV_FILE}"
set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a

SIM_SERVER_HOST="${SIM_SERVER_HOST:-localhost}"
SIM_SERVER_URL="${SIM_SERVER_URL:-https://${SIM_SERVER_HOST}:5001}"
[[ "${SIM_SERVER_HOST}" =~ ^[a-zA-Z0-9.-]+$ ]] || fail "Invalid SIM_SERVER_HOST"
python3 - "${SIM_SERVER_HOST}" "${SIM_SERVER_URL}" <<'PY'
import sys
from urllib.parse import urlsplit
url = urlsplit(sys.argv[2])
assert (url.scheme == 'https' and url.hostname == sys.argv[1] and not url.username and
        not url.password and not url.path and not url.query and not url.fragment), 'Invalid SIM_SERVER_URL origin'
assert url.port is None or 0 < url.port < 65536, 'Invalid SIM_SERVER_URL port'
PY
openssl x509 -in "${ROOT_DIR}/certs/cert.pem" -noout -checkhost "${SIM_SERVER_HOST}" >/dev/null || fail "TLS certificate does not cover SIM_SERVER_HOST"
if [[ "${AUTH_DISABLED:-false}" == true && "${SIM_SERVER_HOST}" != localhost ]]; then
    fail "Shared local login requires localhost; configure OIDC for a multi-user deployment"
fi

# Persist generated broker credentials across rebuilds; never rotate them implicitly.
if [[ ! -f "${ROOT_DIR}/.broker-secrets.env" ]]; then
    python3 - "${ROOT_DIR}/.broker-secrets.env" <<'PY'
import os, secrets, sys
names = ('RABBITMQ_PASSWORD', 'REDIS_PASSWORD', 'KAFKA_APP_PASSWORD', 'KAFKA_ADMIN_PASSWORD',
         'KAFKA_OBSERVER_PASSWORD', 'KAFKA_REGISTRY_PASSWORD')
fd = os.open(sys.argv[1], os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, 'w') as target:
    for name in names:
        target.write(name + '=' + secrets.token_hex(32) + '\n')
PY
fi
chmod 600 "${ROOT_DIR}/.broker-secrets.env"
set -a
source "${ROOT_DIR}/.broker-secrets.env"
set +a

mkdir -p "${ROOT_DIR}/data/resources" "${ROOT_DIR}/data/results" "${ROOT_DIR}/data/logs" "${ROOT_DIR}/data/definitions"/{domains,layers,components,connectors,resources}
chmod a+rwx "${ROOT_DIR}/data/resources" "${ROOT_DIR}/data/results" "${ROOT_DIR}/data/logs"
export KAFKA_TLS_CERT_FILE="${ROOT_DIR}/certs/kafka/cert.pem"
export KAFKA_TLS_KEY_FILE="${ROOT_DIR}/certs/kafka/key.pem"
if [[ ! -f "${KAFKA_TLS_CERT_FILE}" || ! -f "${KAFKA_TLS_KEY_FILE}" ]]; then
    [[ ! -f "${KAFKA_TLS_CERT_FILE}" && ! -f "${KAFKA_TLS_KEY_FILE}" ]] || fail "Incomplete Kafka TLS pair; restore it before proceeding"
    mkdir -p "${ROOT_DIR}/certs/kafka"
    openssl req -x509 -newkey rsa:2048 -nodes -days 365 \
        -keyout "${KAFKA_TLS_KEY_FILE}" -out "${KAFKA_TLS_CERT_FILE}" \
        -subj /CN=broker.kafka.svc.cluster.local \
        -addext 'subjectAltName=DNS:broker,DNS:broker.kafka,DNS:broker.kafka.svc,DNS:broker.kafka.svc.cluster.local' >/dev/null 2>&1
    chmod 600 "${KAFKA_TLS_KEY_FILE}"
fi
python3 "${ROOT_DIR}/scripts/cluster-secrets.py" >/dev/null

AUTH_DISABLED="${AUTH_DISABLED:-false}"
case "${AUTH_DISABLED}" in
    true|false) ;;
    *) fail "AUTH_DISABLED must be true or false" ;;
esac

for variable_name in DB_PASSWORD SESSION_SECRET; do
    require_value "${variable_name}"
done
if [[ "${AUTH_DISABLED}" == "false" ]]; then
    require_value OIDC_CLIENT_ID
    require_value OIDC_CLIENT_SECRET
else
    log "Local login enabled: all visitors share one development account. Keep access local."
fi

if [[ "$(minikube -p "${PROFILE}" status --format='{{.Host}}' 2>/dev/null || true)" != "Running" ]]; then
    fail "Minikube profile '${PROFILE}' is not running. Start it before running this script"
fi

current_context="$(kubectl config current-context 2>/dev/null || true)"
[[ "${current_context}" == "${PROFILE}" ]] || fail \
    "kubectl context is '${current_context:-unset}', expected '${PROFILE}'. Run: kubectl config use-context ${PROFILE}"

log "Using Minikube profile ${PROFILE}"
eval "$(minikube -p "${PROFILE}" docker-env --shell bash)"
docker info >/dev/null

# The web image builds the dashboard itself; its context is the repository root.
build_image "simaas-web:latest" "${ROOT_DIR}" "${ROOT_DIR}/fastapi_app/Dockerfile"
build_image "simservice/simservice:latest" "${ROOT_DIR}/simservice"
build_image "simservice/pandapowerwrapper-wrapper:latest" "${ROOT_DIR}/simservice/PandaPowerWrapper"
build_image "simservice/sumowrapper-wrapper:latest" "${ROOT_DIR}/simservice/cppbase+sumowrapper"

build_image "simaas-mosaik-worker:latest" "${ROOT_DIR}/mosaik/mosaik-worker"

build_image "simservice/controllerwrapper-wrapper:latest" "${ROOT_DIR}/simservice/ControllerWrapper"


log "Preparing Kubernetes credentials"
kubectl create namespace "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -
kubectl create namespace kafka --dry-run=client -o yaml | kubectl apply -f -
kubectl -n "${NAMESPACE}" create secret tls web-tls \
    --cert="${ROOT_DIR}/certs/cert.pem" --key="${ROOT_DIR}/certs/key.pem" \
    --dry-run=client -o yaml | kubectl apply -f -
python3 "${ROOT_DIR}/scripts/cluster-secrets.py" | kubectl apply -f -

encoded_db_password="$(
    python3 - <<'PY'
import os
from urllib.parse import quote

print(quote(os.environ["DB_PASSWORD"], safe=""))
PY
)"

TEMP_DIR="$(mktemp -d)"
chmod 700 "${TEMP_DIR}"

{
    printf 'POSTGRES_USER=%s\n' "simserver"
    printf 'POSTGRES_PASSWORD=%s\n' "${DB_PASSWORD}"
    printf 'POSTGRES_DB=%s\n' "simserver"
} > "${TEMP_DIR}/postgres.env"

{
    printf 'OIDC_CLIENT_ID=%s\n' "${OIDC_CLIENT_ID:-}"
    printf 'OIDC_CLIENT_SECRET=%s\n' "${OIDC_CLIENT_SECRET:-}"
    printf 'SESSION_SECRET=%s\n' "${SESSION_SECRET}"
    printf 'DATABASE_URL=postgresql://simserver:%s@postgres.simservice.svc.cluster.local:5432/simserver\n' \
        "${encoded_db_password}"
} > "${TEMP_DIR}/web.env"

chmod 600 "${TEMP_DIR}/postgres.env" "${TEMP_DIR}/web.env"

kubectl -n "${NAMESPACE}" create secret generic postgres-secret \
    --from-env-file="${TEMP_DIR}/postgres.env" \
    --dry-run=client -o yaml | kubectl apply -f -

kubectl -n "${NAMESPACE}" create secret generic web-secret \
    --from-env-file="${TEMP_DIR}/web.env" \
    --dry-run=client -o yaml | kubectl apply -f -

cleanup
TEMP_DIR=""

log "Applying the full Minikube stack"
kubectl apply -f "${MANIFEST}"
kubectl -n "${NAMESPACE}" set env deployment/web AUTH_DISABLED="${AUTH_DISABLED}"
kubectl -n "${NAMESPACE}" set env deployment/web SESSION_HTTPS_ONLY=true OIDC_REDIRECT_URI="${SIM_SERVER_URL}/auth/callback"
python3 - "${SIM_SERVER_HOST}" <<'PY' | kubectl apply -f -
import json, sys
print(json.dumps({'apiVersion':'networking.k8s.io/v1','kind':'Ingress',
    'metadata':{'name':'simulation-server','namespace':'simservice','annotations':{
        'traefik.ingress.kubernetes.io/router.entrypoints':'websecure,mosaik',
        'traefik.ingress.kubernetes.io/router.tls':'true'}},
    'spec':{'ingressClassName':'traefik','tls':[{'hosts':[sys.argv[1]],'secretName':'web-tls'}],
            'rules':[{'host':sys.argv[1],'http':{'paths':[{'path':'/','pathType':'Prefix',
                'backend':{'service':{'name':'web','port':{'number':5001}}}}]}}]}}))
PY

helm repo add traefik https://traefik.github.io/charts --force-update
helm repo update traefik
helm upgrade --install simaas-ingress traefik/traefik --version 42.3.2 \
    --namespace ingress-system --create-namespace \
    -f "${ROOT_DIR}/simservice/k8s/traefik-values.yaml" --timeout 300s
# Local port-forwarding needs a ready controller, not a LoadBalancer external IP.
kubectl -n ingress-system rollout status deployment/simaas-ingress --timeout=300s

log "Configuring Kafka ACLs"
acl_job="$(kubectl create -f "${ROOT_DIR}/simservice/k8s/kafka-acls.yaml" -o name)"
kubectl -n kafka wait --for=condition=complete "${acl_job}" --timeout=240s
kubectl -n "${NAMESPACE}" rollout status deployment/postgres --timeout=180s

log "Migrating task framework metadata"
migration_job="$(kubectl create -f "${ROOT_DIR}/simservice/k8s/task-framework-migration.yaml" -o name)"
if ! kubectl -n "${NAMESPACE}" wait --for=condition=complete "${migration_job}" --timeout=180s; then
    kubectl -n "${NAMESPACE}" logs "${migration_job}" --all-containers=true || true
    fail "Metadata migration failed; inspect the migration job before continuing"
fi

log "Restarting local-image deployments"
kubectl -n "${NAMESPACE}" rollout restart \
    deployment/web \
    deployment/log-consumer \
    deployment/simservice \
    deployment/mosaik-worker \
    deployment/mosaik-gui

log "Deployment submitted"
kubectl -n kafka get pods
kubectl -n "${NAMESPACE}" get pods

cat <<EOF

Next terminals:
  minikube -p ${PROFILE} mount "${ROOT_DIR}/data:/data"
  kubectl -n ingress-system port-forward service/simaas-ingress 5001:5001 8002:8002

Then open ${SIM_SERVER_URL}
The Mosaik editor uses https://${SIM_SERVER_HOST}:8002/mosaik/ with the web login.
EOF
