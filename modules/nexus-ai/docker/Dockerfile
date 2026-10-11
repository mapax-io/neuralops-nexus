# The new nexus-ai — a standalone image for the rebuild (docs/NEXUS-AI-REVAMP.md
# §1.3 "New module, final name from day one"). The legacy service keeps running
# from the shared neuralops image; this one is only what nucleus gets pointed
# at to test, until switch-over.
#
# No public port by design: nucleus reaches it container-to-container on the
# Docker network; the internal key check is the second lock.
FROM python:3.13-slim

ARG UID=1000
RUN useradd -m -u ${UID} nexus

WORKDIR /nexus/ai

# The lock file is the full `pip freeze` of the pinned set — reproducible builds.
COPY requirements.txt requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock

COPY . .

ENV PYDANTIC_AI_NO_BANNER=1 \
    PYTHONUNBUFFERED=1

USER nexus
EXPOSE 8000
CMD ["uvicorn", "fastapi_app.main:app", "--host", "0.0.0.0", "--port", "8000"]
