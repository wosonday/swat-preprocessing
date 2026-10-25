# ---------- Stage 1: builder ----------
FROM python:3.12-slim-bookworm AS builder
COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=0
WORKDIR /app

# (a) Chỉ cài thư viện: layer được cache khi chỉ sửa mã
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project --no-editable --extra geo --extra app

# (b) Copy mã rồi cài chính dự án
COPY README.md ./
COPY swatprep ./swatprep
COPY app ./app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-editable --extra geo --extra app

# ---------- Stage 2: runtime ----------
FROM python:3.12-slim-bookworm
RUN apt-get update \
 && apt-get install -y --no-install-recommends libexpat1 \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --create-home --uid 1000 swat
WORKDIR /app
COPY --from=builder --chown=swat:swat /app/.venv /app/.venv
COPY --chown=swat:swat app ./app
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
USER swat
EXPOSE 8501
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')"
CMD ["streamlit", "run", "app/Home.py", "--server.address=0.0.0.0"]