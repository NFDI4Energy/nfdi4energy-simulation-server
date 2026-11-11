# Build context is the repository root: docker build -f fastapi_app/Dockerfile .

# Stage 1: build the Svelte dashboard so the checkout never needs a committed bundle.
FROM node:22-alpine AS dashboard

WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# vite.config.js writes to ../fastapi_app/static/svelte-dist relative to /frontend.
RUN mkdir -p /fastapi_app/static && npm run build

# Stage 2: the web application and the log consumer.
FROM python:3.12-slim

ENV RABBITMQ_HOST=rabbitmq \
    REDIS_HOST=redis \
    RESULTS_DIR=/data/results \
    RESOURCES_DIR=/data/resources \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
# Import the canonical fastapi_app package while retaining webapp:app from WORKDIR.
ENV PYTHONPATH=/

COPY fastapi_app/requirements.txt /tmp/

# install pinned requirements (binary wheels only; no compiler in the image)
RUN pip install --only-binary=:all: -r /tmp/requirements.txt

COPY fastapi_app/ /fastapi_app
COPY --from=dashboard /fastapi_app/static/svelte-dist /fastapi_app/static/svelte-dist

WORKDIR /fastapi_app

# Verify ORM imports and migration against the actual image dependencies, without services or credentials.
RUN python -c "from fastapi_app.persistence.database import create_database, init_db; from fastapi_app.persistence.migrate_framework import migrate; engine, _ = create_database('sqlite:///:memory:'); init_db(engine); migrate(engine); engine.dispose()"

# Run as an unprivileged user. UID 1000 matches the owner of the Minikube data mount.
RUN groupadd --gid 1000 simaas && useradd --uid 1000 --gid 1000 --no-create-home --shell /usr/sbin/nologin simaas \
    && mkdir -p /data /certs && chown simaas:simaas /data
USER simaas

# expose the app port
EXPOSE 5001

# run the app server
CMD ["uvicorn", "webapp:app", "--host", "localhost", "--port", "5001", "--proxy-headers", "--ssl-keyfile", "/certs/key.pem", "--ssl-certfile", "/certs/cert.pem"]
