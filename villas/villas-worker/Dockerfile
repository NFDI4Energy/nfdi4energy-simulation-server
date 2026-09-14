FROM ghcr.io/astral-sh/uv:python3.13-trixie-slim

WORKDIR /app

COPY villas/villas-worker/ ./

RUN uv sync --no-dev

CMD ["uv", "run", "python", "villas_worker.py"]
