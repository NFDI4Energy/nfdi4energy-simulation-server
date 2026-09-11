# Temporary Local Sign-In

Set AUTH_DISABLED=true on the web deployment to make the existing Sign in button
create a shared local development session and open the dashboard without OIDC.
The default remains false. SESSION_SECRET and PostgreSQL are still required.

This is for a trusted local environment only: anyone who can reach the web service
can sign in as the same development user and access that user's tasks. Existing
OIDC users' tasks remain private; they are not reassigned to the development user.
Keep the service restricted to your machine while this option is enabled.

Build the changed web image first:

```bash
python3 build-changed-minikube.py
kubectl -n simservice set env deployment/web AUTH_DISABLED=true
kubectl -n simservice rollout status deployment/web --timeout=300s
kubectl -n simservice port-forward service/web 5001:5001
```

Open https://localhost:5001 and click Sign in. No frontend change or wrapper rebuild
is required for this feature. The incremental builder may also select other images
if they have unrelated pending changes.

To restore OIDC:

```bash
kubectl -n simservice set env deployment/web AUTH_DISABLED=false
kubectl -n simservice rollout status deployment/web --timeout=300s
```

OIDC credentials must be configured before restoring authentication. Existing
development sessions are rejected once the authentication-enabled pods take over.
Local tasks stay in the database and are accessible again if local mode is enabled.
No credentials, shared Kubernetes manifests, or production defaults are changed.
