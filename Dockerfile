# syntax=docker/dockerfile:1
# musl (DHI uv is a glibc build, so this stage keeps Astral's static uv)
FROM ghcr.io/astral-sh/uv:0.12.17@sha256:10787c682e4184e4f290de1171fd4703dc63de99221f10fe1c99002ce7fa9acc AS uv-musl
FROM dhi.io/uv:0@sha256:1ad16dfed260fb020ea8e1c5bb02c97059f8b1dbe6e669ded5a163ddbce6e73f AS uv-glibc

FROM dhi.io/python:3.14-alpine-dev@sha256:a40c90f9eb46f8a1c8d56ea1bb990c556677622e4b7d3d7130d713a9de4b4b1d AS builder
COPY --from=uv-musl /uv /uvx /usr/local/bin/
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
RUN uv run ruff check src tests \
    && uv run basedpyright --threads 1 \
    && uv run bandit -r src -ll \
    && uv run pytest --cov=overheadadsb --cov-report=term-missing

FROM dhi.io/python:3.14-alpine@sha256:4361d30a5f505dd5509622eff5c7bef79afa798b4f3eedd3f5cb1abc92be9168 AS runtime
COPY --from=builder --chown=nonroot:nonroot /app /app
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
WORKDIR /app
EXPOSE 8003
ENV UVICORN_PORT=8003
CMD ["/app/.venv/bin/uvicorn", "overheadadsb.main:app", "--host", "0.0.0.0"]

# glibc
FROM dhi.io/python:3.14-dev@sha256:87a27707f543146a9f5fb4452a9f6f013e06f518cd0d5e4440d0b83aa783ce86 AS builder-deb
COPY --from=uv-glibc /usr/local/bin/uv /usr/local/bin/uvx /usr/local/bin/
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev
COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

FROM goreleaser/nfpm:latest@sha256:a662cb167d7b6d3a83920c83d76b12d02b8ac5dd2c13e5c62c15270b23f6df0c AS nfpm
FROM builder-deb AS package
COPY --from=nfpm /usr/bin/nfpm /usr/local/bin/nfpm
COPY packaging/nfpm.yaml packaging/ /app/packaging/
RUN VERSION="$(python -c 'import tomllib; print(tomllib.load(open("pyproject.toml","rb"))["project"]["version"])')" \
    && export VERSION \
    && mkdir -p /dist \
    && nfpm package --config packaging/nfpm.yaml --packager deb \
         --target "/dist/overheadadsb_${VERSION}.deb"
