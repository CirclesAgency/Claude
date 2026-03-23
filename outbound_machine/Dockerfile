FROM python:3.11-slim

# Install system dependencies for lxml, psycopg2, and Playwright
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    libxml2-dev \
    libxslt-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency spec first (cache layer)
COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[dev]"

# Install Playwright browsers (only if screenshots enabled)
# Comment this out if you don't need screenshots to keep image lean
RUN playwright install chromium --with-deps || true

# Copy application
COPY . .

# Default: run the CLI
ENTRYPOINT ["python", "-m", "app.cli.commands"]
CMD ["--help"]
