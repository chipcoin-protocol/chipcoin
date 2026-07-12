FROM python:3.11-slim AS builder

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY pyproject.toml setup.py MANIFEST.in README.md ./
COPY src ./src
COPY vendor ./vendor

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libc6-dev \
    && python -m pip wheel --no-cache-dir --wheel-dir /wheels . \
    && rm -rf /var/lib/apt/lists/*

FROM python:3.11-slim AS runtime

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY --from=builder /wheels /wheels
COPY docker/entrypoint.sh /usr/local/bin/chipcoin-entrypoint

RUN set -eux; \
    python -m pip install --no-cache-dir --no-index --find-links=/wheels chipcoin-v2; \
    python -m pip check; \
    python -m pip uninstall -y setuptools wheel; \
    rm -rf /wheels /root/.cache/pip; \
    chmod +x /usr/local/bin/chipcoin-entrypoint; \
    if dpkg-query -W -f='${binary:Package}\n' gcc libc6-dev 2>/dev/null | grep -q .; then \
        echo "unexpected build package remains in runtime"; \
        exit 1; \
    fi; \
    python -c 'import importlib.util, sysconfig; from pathlib import Path; purelib = Path(sysconfig.get_paths()["purelib"]); paths = ("setuptools/_vendor/wheel", "setuptools/_vendor/jaraco/context.py", "setuptools/_vendor/jaraco/context"); missing_vendor = all(not (purelib / path).exists() for path in paths); missing_modules = all(importlib.util.find_spec(module) is None for module in ("setuptools", "wheel")); raise SystemExit(0 if missing_vendor and missing_modules else 1)'

CMD ["chipcoin", "--help"]
