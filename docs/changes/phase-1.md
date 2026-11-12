# Phase 1: foundation in SimaaS (tests, CI, image, login)

## Goal

Make later rework safe: no runtime data or build output in Git, a reproducible
web image on a supported Python, a backend test suite with CI, and a login that
cannot be bypassed on a public deployment.

## Branches and base

Phase 0 was still in review, so every unit is stacked on the previous one.
After Phase 0 merges, rebase `roadmap/phase-1a-repo-hygiene` onto `main`; the
others follow without conflicts.

**Rebased on 2026-11-12** onto `main` @ 724c9bf together with Phase 0 (see
`phase-0.md`). Decisions taken during the rebase: Mosaik stays enabled by
default (step 4 revised), the `SESSION_HTTPS_ONLY` flag from `main` is kept and
step 12 only adds `SameSite=Lax` next to it, and the steps `main` pre-empted
(38, 39, 41, 47, 55) are marked `[~]` in the roadmap with what is still missing.
The hidden test suite the maintainer mentioned for those commits is not in the
repository; Phase 5 should start by bringing it in.

| Unit | Branch | Base | Steps |
|---|---|---|---|
| 1a | `roadmap/phase-1a-repo-hygiene` | `roadmap/phase-0c-pandapower-guard` | 7, 8 (untracking) |
| 1b | `roadmap/phase-1b-docker-build` | 1a | 8 (image build), 9 |
| 1c | `roadmap/phase-1c-backend-tests-ci` | 1b | 10, 11 |
| 1d | `roadmap/phase-1d-auth-hardening` | 1c | 12, phase docs |

The agent prompt suggested three units (1a: 7+8, 1b: 9–11, 1c: 12). The
deletions were split into their own branch as CLAUDE.md asks, which gives four.

## Steps

### 1a (deletions only)

| Step | Commit | What changed |
|---|---|---|
| 7 | `chore(data): stop tracking runtime task data` | `git rm -r --cached data/resources data/results` (113 files); local copies stay for the Minikube mount; `.gitkeep` in both directories. `data/definitions`, `data/simulators`, `data/layers`, `data/config.properties` are SimService configuration and stay. |
| 8 | `chore(frontend): stop tracking the built dashboard` | `git rm -r --cached fastapi_app/static/svelte-dist`, `.gitignore` entry; carries the maintainers' "agreed" note in `CLAUDE.md`. |

### 1b

| Step | Commit | What changed |
|---|---|---|
| 8 | `build(web): build the dashboard inside the image` | `fastapi_app/Dockerfile` gains a `node:22-alpine` stage (`npm ci && npm run build`); build context is the repository root with a `.dockerignore`; `build-minikube.sh` passes `--file` and no longer runs npm on the host; `docker-compose.yml` context updated; `webapp.mount_dashboard` mounts `/dashboard` only when the bundle exists and logs how to build it otherwise; `test_dashboard_mount.py`. |
| 9 | `build(workers): pin example worker requirements` | `task_queue/requirements.txt` pinned (the Mosaik worker already was). |
| 9 | `build(web): Python 3.12 base image, pinned requirements, non-root user` | `python:3.12-slim`, `fastapi_app/requirements.txt` pinned to the versions a fresh install resolved on 2026-11-11, `pip install --only-binary=:all:`, user `simaas` (UID/GID 1000), `/data` owned by that user in the image. `WORKDIR /fastapi_app` and `PYTHONPATH=/` are kept so the Kubernetes/Compose commands are unchanged. |

### 1c

| Step | Commit | What changed |
|---|---|---|
| 10 | `test(backend): add settings, storage, scenario, submission and auth tests` | Five test modules (settings, storage containment, DaceDSX scenario validation, `SubmissionService` end to end with SQLite + fake Redis/queue, auth routes in local mode), `pytest.ini`, `requirements-dev.txt`. |
| 11 | `build(frontend): add svelte-check` | `svelte-check` 3 devDependency, `npm run check` (`--threshold error`), two JSDoc annotations that fix the three type errors it reported; lockfile update. |
| 11 | `ci: lint, backend tests, frontend checks and image build` | `.github/workflows/ci.yml` with jobs `backend` (flake8 + pytest), `frontend` (npm test, svelte-check, vite build), `image` (compose config, web image build, smoke test); `.flake8`. |

### 1d

| Step | Commit | What changed |
|---|---|---|
| 12 | `feat(auth): forbid AUTH_DISABLED outside development, secure session cookie` | `SIMAAS_ENV` setting (`development` \| `production`, default `production`); `Settings.validate()` refuses `AUTH_DISABLED=true` unless development; `SessionMiddleware(https_only=settings.session_https_only, same_site="lax")`, where `SESSION_HTTPS_ONLY` comes from `main` and `build-minikube.sh` sets it to `true`; `build-minikube.sh`, `docker-compose.yml`, `.env.example`, README and guide updated. |
| 12 | `test(auth): login modes, production guard and cookie flags` | Tests for the guard, the environment parsing and the cookie attributes (Secure, HttpOnly, SameSite=Lax, not sent over HTTP). |
| – | `docs: add phase 1 notes` | This file, CHANGELOG, roadmap ticks. |

## Assumptions

- **B1** Runtime data was removed from the index only (`--cached`); the working
  copies remain for the running Minikube mount.
- **B2** `SIMAAS_ENV` defaults to `production`. Local users must add
  `SIMAAS_ENV=development` to `.env`; existing local `.env` files with
  `AUTH_DISABLED=true` will fail the build script until they do, which is the
  intended signal.
- **B3** The web image runs as UID 1000. The Minikube mount is owned by the VM's
  `docker` user (UID 1000), so writes to `/data` should keep working, but this was
  not exercised against a cluster here. If the pod cannot write `/data`, that is
  the file-permission work of step 33 (Phase 4) arriving early; `fsGroup: 1000`
  on the pod would be the stop-gap.
- **B4** `svelte-check` runs with `--threshold error`; the five unused-CSS warnings
  are pre-existing and left alone.
- **B5** Only direct dependencies are pinned (`==`), not a full freeze. pydantic
  resolved to 2.14.3; the code still uses the v1 `root_validator` API, which
  pydantic 2 supports with a deprecation warning (step 34 migrates it).
- flake8 enforces only the pyflakes rules (`select = E9,F`); the code base has
  ~50 style findings that are not fixed in passing. `task_queue/tasks.py` (legacy
  MVS/Celery worker, not built or deployed) is excluded from the unused-name checks.
- The maintainers' agreement to assumptions 1–5 does not affect this phase.
- The deployment guide still tells readers to switch to the `daceds+mosaik`
  branch; that text predates the roadmap and was not changed here.

## Acceptance test

**1a:**

```bash
git ls-files data/results data/resources fastapi_app/static/svelte-dist | wc -l
```

Expected: `2` (only the two `.gitkeep` files).

**1b:**

```bash
docker build -f fastapi_app/Dockerfile -t simaas-web:test . \
  && docker run --rm simaas-web:test sh -c 'id -u; python --version; test -f static/svelte-dist/index.html && echo bundle-ok; python -c "import webapp"'
```

Expected: `1000`, `Python 3.12.x`, `bundle-ok`, no import error.

**1c** (with `pip install -r requirements-dev.txt` and `npm ci` in `frontend/`):

```bash
flake8 fastapi_app task_queue mosaik && python -m pytest -q
```

Expected: no flake8 output, `66 passed`.

```bash
npm --prefix frontend test && npm --prefix frontend run check && npm --prefix frontend run build
```

Expected: 14 node tests pass, `svelte-check found 0 errors`, Vite build succeeds.

**1d:**

```bash
AUTH_DISABLED=true SIMAAS_ENV=production SESSION_SECRET=x python -c "from fastapi_app.core.settings import Settings; Settings.from_env().validate()"
```

Expected: `RuntimeError: AUTH_DISABLED=true is only allowed with SIMAAS_ENV=development`.
With `SIMAAS_ENV=development` the same command succeeds.

What was **not** run: `build-minikube.sh` against a cluster (it is a full
deployment including the SUMO build) and the CI workflow itself (needs a push).
The workflow file was parsed with PyYAML; each job's commands were run locally
as listed above.

## Manual steps for humans

1. **Step 12, OIDC client:** register a client at NFDI AAI (regapp.nfdi-aai.de)
   for the future public domain. Needed values: client type confidential,
   redirect URI `https://<domain>/auth/callback`, scopes `openid profile email`,
   discovery URL as in `Settings.oidc_discovery_url`. Put the issued ID/secret in
   the deployment's secret (`web-secret`), never in Git.
2. **Step 11:** push the branch and watch the first CI run; the `image` job
   needs ~5 minutes for the node and pip layers.
3. Local machines: add `SIMAAS_ENV=development` to `.env` before the next
   `build-minikube.sh`.

## Open questions

- Remove `task_queue/tasks.py` (legacy MVS/Celery worker)? It imports packages
  that are not installed anywhere in this repository.
- Should the `image` CI job also build the DaceDSX wrapper images? Left out
  because those move upstream in Phase 2/3.

## Review notes

Read in this order:

1. 1a: `git show --stat` of both commits; nothing else to read.
2. 1b: `fastapi_app/Dockerfile` (whole file), then `webapp.mount_dashboard`, then
   the `build-minikube.sh` diff.
3. 1c: `.github/workflows/ci.yml`, `.flake8`, then the tests, starting with
   `test_submission.py` (the only one with real behaviour under test).
4. 1d: `Settings.validate()` and `SESSION_COOKIE` in `webapp.py`, then
   `test_auth.py`.

Look at: the `.dockerignore` keeps `fastapi_app/tests` out of the image; the
`image` job's smoke test is the same command as the 1b acceptance test.
