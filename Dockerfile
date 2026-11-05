FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY app.py research.py store.py apple.py index.html ./
COPY static/ static/
COPY examples/ examples/
COPY data/apps.jsonl.gz data/reviews.jsonl.gz data/manifest.json data/
RUN .venv/bin/python -c "import store; store.initialize()"
ENV PORT=8080
EXPOSE 8080
CMD [".venv/bin/python", "app.py"]
