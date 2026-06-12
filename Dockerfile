# FlowOps control plane. Minimal scaffold image.
FROM python:3.12-slim

# uv for fast, reproducible installs.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN uv pip install --system --no-cache .

ENV FLOWOPS_PROFILE=dev
EXPOSE 8000
# Non-root by default (security: no root containers in prod images).
RUN useradd -m flowops
USER flowops

CMD ["uvicorn", "flowops.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
