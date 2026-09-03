FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src/ src/
RUN uv sync --frozen --no-dev

ENTRYPOINT ["uv", "run", "run-pipeline"]
CMD ["--config", "src/odk_to_121/infra/configs/registrations.yaml", "--run-target", "prod"]
