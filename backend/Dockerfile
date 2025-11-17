# Lightweight production image for the Django backend (Connectwell)
# Build with: docker build -t connectwell-backend:latest .
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install build deps and compile wheels in builder stage
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev gcc curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src

# Copy requirements and install into a dedicated prefix
COPY ../requirements.txt /src/requirements.txt
RUN python -m pip install --upgrade pip setuptools wheel
RUN python -m pip install --prefix=/install -r /src/requirements.txt

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Create app directory and user
WORKDIR /app
COPY .. /app
RUN useradd --create-home appuser && chown -R appuser /app
USER appuser

ENV PATH="/home/appuser/.local/bin:$PATH"

# Copy entrypoint and make executable
COPY --chown=appuser:appuser entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000

# Default command runs the entrypoint which will apply migrations/collectstatic then exec Daphne
ENTRYPOINT ["/entrypoint.sh"]
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "connectwell.asgi:application"]
