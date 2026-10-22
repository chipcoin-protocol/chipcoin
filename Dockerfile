ARG SOURCE_DATE_EPOCH=1792069138

FROM python:3.11.17-trixie@sha256:50cfccc707e8721201ee018bfd7f6a85d8eacf49c4f9f75833a2aba09a10411f AS builder

ARG SOURCE_DATE_EPOCH

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY pyproject.toml setup.py MANIFEST.in README.md ./
COPY src ./src
COPY vendor ./vendor
COPY docker/requirements-build.lock ./requirements-build.lock

RUN set -eux; \
    umask 022; \
    command -v gcc; \
    dpkg-query -W -f='${binary:Package}=${Version}\n' gcc libc6-dev; \
    python -m pip wheel --no-cache-dir --require-hashes --wheel-dir /wheels -r requirements-build.lock; \
    python -m pip install --no-compile --no-index --find-links=/wheels setuptools==68.1.2 wheel==0.42.0; \
    SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH}" python -m pip wheel --no-cache-dir --no-build-isolation --no-deps --wheel-dir /wheels .; \
    find /wheels -depth -exec touch -h -d "@${SOURCE_DATE_EPOCH}" {} +

FROM python:3.11.17-slim-trixie@sha256:0dd364ba7e10242f07755449e3a3d0e35f9efd987952737b90def6709ab0c5ce AS runtime

ARG SOURCE_DATE_EPOCH

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN --mount=type=bind,from=builder,source=/wheels,target=/wheels,ro \
    --mount=type=bind,source=docker/requirements-build.lock,target=/tmp/requirements-build.lock,ro \
    --mount=type=bind,source=docker/entrypoint.sh,target=/tmp/chipcoin-entrypoint,ro \
    set -eux; \
    python -m pip install --no-compile --no-cache-dir --no-index --find-links=/wheels --require-hashes -r /tmp/requirements-build.lock; \
    python -m pip install --no-compile --no-cache-dir --no-deps /wheels/chipcoin_v2-*.whl; \
    python -m pip check; \
    python -m pip uninstall -y setuptools wheel; \
    install -m 0755 /tmp/chipcoin-entrypoint /usr/local/bin/chipcoin-entrypoint; \
    if dpkg-query -W -f='${binary:Package}\n' gcc libc6-dev 2>/dev/null | grep -q .; then \
        echo "unexpected build package remains in runtime"; \
        exit 1; \
    fi; \
    find /usr/local/lib/python3.11/site-packages /usr/local/bin -depth \
         -exec touch -h -d "@${SOURCE_DATE_EPOCH}" {} +; \
    touch -h -d "@${SOURCE_DATE_EPOCH}" /etc /tmp /usr/local /usr/local/lib /usr/local/lib/python3.11 /app; \
    python -c 'import importlib.util, sysconfig; from pathlib import Path; purelib = Path(sysconfig.get_paths()["purelib"]); paths = ("setuptools/_vendor/wheel", "setuptools/_vendor/jaraco/context.py", "setuptools/_vendor/jaraco/context"); missing_vendor = all(not (purelib / path).exists() for path in paths); missing_modules = all(importlib.util.find_spec(module) is None for module in ("setuptools", "wheel")); raise SystemExit(0 if missing_vendor and missing_modules else 1)'

CMD ["chipcoin", "--help"]
