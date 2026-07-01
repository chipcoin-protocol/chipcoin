FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY pyproject.toml setup.py MANIFEST.in README.md ./
COPY src ./src
COPY vendor ./vendor
COPY docker ./docker
COPY docker/entrypoint.sh /usr/local/bin/chipcoin-entrypoint

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libc6-dev \
    && pip install --no-cache-dir . \
    && apt-get purge -y --auto-remove gcc libc6-dev \
    && rm -rf /var/lib/apt/lists/*
RUN chmod +x /usr/local/bin/chipcoin-entrypoint

CMD ["chipcoin", "--help"]
