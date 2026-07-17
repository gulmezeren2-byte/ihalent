# ihalent MCP server, containerised.
#
# The image runs `ihalent-mcp` over stdio, so any MCP-speaking runtime — Claude
# Desktop/Code, or Glama's in-browser inspector — can query tender-award
# intelligence without a local Python install:
#
#   docker build -t ihalent .
#   docker run --rm -i ihalent
#
# (For the CLI instead of the server, override the entrypoint:
#   docker run --rm -v "$PWD:/work" -w /work --entrypoint ihalent ihalent --help)
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY . /app

# Install the package with the MCP extra pinned in pyproject.
RUN pip install ".[mcp]"

# Drop privileges: the server is read-only against the data it is given.
RUN useradd --create-home --uid 1000 ihalent
USER ihalent

# stdio transport — the runtime speaks MCP over stdin/stdout.
ENTRYPOINT ["ihalent-mcp"]
