ARG SOURCE=https://github.com/bobbravo2/ReefProof
ARG REVISION=unknown
ARG VERSION=0.1.0
ARG CREATED=unknown

FROM python:3.13-alpine@sha256:c25cd44f45df1279a2cba589e67dfcd9db04647ea483b117a7de8b1a99bdfb23 AS builder

ARG SOURCE
ARG REVISION
ARG CREATED

COPY --from=ghcr.io/astral-sh/uv:0.11.32@sha256:0d127b3a7049b879a6e18a79c7f33fea59aa83c226464248f89cfb716a6b96f5 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --no-install-project

COPY src ./src
COPY scripts/write-build-identity.py /tmp/write-build-identity.py
RUN python /tmp/write-build-identity.py \
      --output /app/src/reefproof/_build_identity.py \
      --revision "$REVISION" \
      --source "$SOURCE" \
      --created "$CREATED"
RUN uv sync --locked --no-dev --no-editable
RUN find /app/.venv -type f \
      \( -name direct_url.json -o -name uv_cache.json \) \
      -delete

FROM python:3.13-alpine@sha256:c25cd44f45df1279a2cba589e67dfcd9db04647ea483b117a7de8b1a99bdfb23 AS runtime

ARG SOURCE
ARG REVISION
ARG VERSION
ARG CREATED

LABEL org.opencontainers.image.title="ReefProof" \
      org.opencontainers.image.description="Read-only configuration assurance for living systems" \
      org.opencontainers.image.source="$SOURCE" \
      org.opencontainers.image.revision="$REVISION" \
      org.opencontainers.image.version="$VERSION" \
      org.opencontainers.image.created="$CREATED"

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    REEFPROOF_ENVIRONMENT=production \
    REEFPROOF_DATA_DIRECTORY=/var/lib/reefproof

RUN addgroup --system reefproof \
    && adduser --system --ingroup reefproof --home /nonexistent --shell /sbin/nologin reefproof \
    && mkdir -p /var/lib/reefproof \
    && chown reefproof:reefproof /var/lib/reefproof

WORKDIR /app
COPY --from=builder --chown=reefproof:reefproof /app/.venv /app/.venv

USER reefproof
VOLUME ["/var/lib/reefproof"]
ENTRYPOINT ["reefproof"]
CMD ["version"]
