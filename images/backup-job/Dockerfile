FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive

# Install pg_dump and small utilities, pin versions where practical
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       postgresql-client \
       ca-certificates \
       curl \
       unzip \
       libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install AWS CLI v2
RUN set -eux; \
    ARCH=$(dpkg --print-architecture); \
    case "$ARCH" in \
      amd64) AWS_ARCH="x86_64" ;; \
      arm64) AWS_ARCH="aarch64" ;; \
      *) AWS_ARCH="x86_64" ;; \
    esac; \
    curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-${AWS_ARCH}.zip" -o /tmp/awscliv2.zip; \
    unzip /tmp/awscliv2.zip -d /tmp; \
    /tmp/aws/install --update; \
    rm -rf /tmp/aws /tmp/awscliv2.zip

# Create a non-root user for safety
RUN useradd --create-home --shell /bin/sh backup

WORKDIR /backup
COPY entrypoint.sh /backup/entrypoint.sh
RUN chmod 750 /backup/entrypoint.sh && chown -R backup:backup /backup

USER backup
ENTRYPOINT ["/backup/entrypoint.sh"]
