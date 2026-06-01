FROM python:3.12-slim

# Install uv (fast package installer/resolver)
RUN pip install --no-cache-dir uv

WORKDIR /app

# Copy dependency manifests first so Docker can cache the install layer
COPY pyproject.toml uv.lock ./

# Install production deps into a virtualenv under /app/.venv
# --frozen: respect the lock exactly; --no-dev: skip test/lint tooling
RUN uv sync --frozen --no-dev

# Put the virtualenv on PATH so uvicorn is found at CMD time
ENV PATH="/app/.venv/bin:$PATH"

# Copy the rest of the project (see .dockerignore for exclusions)
COPY api/ api/
COPY controller/ controller/
COPY contracts/ contracts/

# Non-root user for container security
RUN useradd --no-create-home --shell /bin/false gcrah
USER gcrah

EXPOSE 8080

# Shell form so ${PORT:-8080} expands at runtime.
# --app-dir . ensures "api" resolves to our package, not a system one.
CMD ["sh", "-c", "uvicorn api.server:app --host 0.0.0.0 --port ${PORT:-8080} --app-dir ."]
