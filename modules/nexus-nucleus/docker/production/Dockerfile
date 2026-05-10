# Stage 1: Build dependencies
FROM python:3.11-slim as builder

WORKDIR /build

# Install build tools for psycopg2 / other C-extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Create the virtual environment in the specific path
ENV VIRTUAL_ENV=/opt/venv/nexus-env
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Install requirements into the venv
# Note: We pull this from the context root as discussed
# COPY requirements.txt .
COPY apps/nucleus/docker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2: Final Runtime
FROM python:3.11-slim

# 1. Setup the 'ubuntu' user and sudo permissions
RUN set -eux; \
    apt-get update && apt-get install -y --no-install-recommends sudo libpq-dev; \
    getent passwd ubuntu >/dev/null 2>&1 || adduser --disabled-password --gecos '' ubuntu; \
    usermod -aG sudo ubuntu; \
    grep -q '^%sudo ALL=(ALL) NOPASSWD:ALL' /etc/sudoers || echo '%sudo ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers; \
    # Create the app directory and give ubuntu ownership BEFORE we switch users
    mkdir -p /app && chown ubuntu:ubuntu /app; \
    rm -rf /var/lib/apt/lists/*

# 2. Copy the Virtual Environment from the builder
COPY --from=builder /opt/venv/nexus-env /opt/venv/nexus-env
ENV VIRTUAL_ENV=/opt/venv/nexus-env
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

WORKDIR /app

# 3. Switch to the ubuntu user
USER ubuntu

# WE REMOVED THE COPY HERE. 
# The code will be provided by the 'volumes' in docker-compose.

# 4. Command to run the app
# --reload is key here because it watches the ATTACHED volume for changes.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--proxy-headers"]