FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /workspace
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY examples ./examples
RUN uv sync --locked --no-dev

ENTRYPOINT ["uv", "run", "dagwright"]
CMD ["compile", "examples/customer-analytics/dataproduct.yaml", "--output", "/output"]
