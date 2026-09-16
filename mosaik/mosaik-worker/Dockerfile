FROM ghcr.io/astral-sh/uv:python3.13-trixie-slim
WORKDIR /app
COPY requirements.txt ./
RUN uv pip install --system --no-cache -r requirements.txt
COPY mosaik_worker.py ./
ENV PYTHONUNBUFFERED=1
CMD ["python", "mosaik_worker.py"]
