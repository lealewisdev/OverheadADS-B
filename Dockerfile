# syntax=docker/dockerfile:1
# musl (DHI uv is a glibc build, so this stage keeps Astral's static uv)
FROM dhi.io/python:3.14-alpine-dev@sha256:7041921325cdec555e8daf4c1b01c0caf2e09bd0eb15748d55b42e4aa0516324 AS builder
COPY --from=ghcr.io/astral-sh/uv:0.12.17@sha256:10787c682e4184e4f290de1171fd4703dc63de99221f10fe1c99002ce7fa9acc /uv /uvx /usr/local/bin/
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev
COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

FROM builder AS test
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --group dev
RUN uv run ruff check src scripts \
    && uv run basedpyright --threads 1 \
    && uv run bandit -r src scripts -ll \
    && uv run pytest --cov=overheadadsb --cov-report=term-missing

FROM dhi.io/python:3.14-alpine@sha256:9d1e11476965ff48627fb752e1be15a22866856cf12a907f5fc7448e536fc0ba AS runtime
COPY --from=builder --chown=nonroot:nonroot /app /app
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
WORKDIR /app
EXPOSE 8003
CMD ["/app/.venv/bin/uvicorn", "overheadadsb.main:app", "--host", "0.0.0.0", "--port", "8003"]

# glibc
FROM dhi.io/python:3.14-dev@sha256:cc2a26e03005f5eaa345a34efaa48d1c672186dc27b74bf566804ce7fd5b8afb AS builder-deb
COPY --from=dhi.io/uv:0@sha256:b6abd484c3ec23494ffc6c16bcfca9276a59b4c50389a4463310aa252a156040 /usr/local/bin/uv /usr/local/bin/uvx /usr/local/bin/
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev
COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

FROM goreleaser/nfpm@sha256:a662cb167d7b6d3a83920c83d76b12d02b8ac5dd2c13e5c62c15270b23f6df0c AS nfpm
FROM builder-deb AS package
COPY --from=nfpm /usr/bin/nfpm /usr/local/bin/nfpm
COPY nfpm.yaml packaging/ /app/packaging/
ARG VERSION
RUN nfpm package --config nfpm.yaml --packager deb --target /dist/overheadadsb_${VERSION}.deb
