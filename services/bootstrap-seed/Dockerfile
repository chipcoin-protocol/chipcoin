FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

CMD ["python", "-m", "bootstrap_seed.app"]
