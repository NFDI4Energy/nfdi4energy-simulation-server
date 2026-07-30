# Minikube Deployment

The deployment manifest references two Kubernetes Secrets that are intentionally
not stored in Git. Load the local environment and create the Secrets before
applying the stack:

```bash
set -a
source .env
set +a

kubectl create namespace simservice --dry-run=client -o yaml \
  | kubectl apply -f -

kubectl -n simservice create secret generic postgres-secret \
  --from-literal=POSTGRES_USER=simserver \
  --from-literal=POSTGRES_PASSWORD="${DB_PASSWORD}" \
  --from-literal=POSTGRES_DB=simserver \
  --dry-run=client -o yaml \
  | kubectl apply -f -

kubectl -n simservice create secret generic web-secret \
  --from-literal=OIDC_CLIENT_ID="${OIDC_CLIENT_ID}" \
  --from-literal=OIDC_CLIENT_SECRET="${OIDC_CLIENT_SECRET}" \
  --from-literal=SESSION_SECRET="${SESSION_SECRET}" \
  --from-literal=DATABASE_URL="postgresql://simserver:${DB_PASSWORD}@postgres.simservice.svc.cluster.local:5432/simserver" \
  --dry-run=client -o yaml \
  | kubectl apply -f -

kubectl apply -f simservice/k8s/minikube-full-stack.yaml
```

Keep `.env` local; use `.env.example` as the list of required values. The root
`build-minikube.sh` script performs these steps and builds all local images.
