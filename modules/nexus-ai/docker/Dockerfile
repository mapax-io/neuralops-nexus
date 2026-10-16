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
# It includes torch==<ver>+cpu (the CPU-only build, ~200 MB instead of ~6 GB of
# CUDA wheels), which only exists on PyTorch's own index — hence the extra-index-url.
# To regenerate the lock, see docs/CHANGE-PROMPT.md (install CPU torch first,
# then -r requirements.txt, then pip freeze).
COPY requirements.txt requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock \
    --extra-index-url https://download.pytorch.org/whl/cpu

COPY . .

ENV PYDANTIC_AI_NO_BANNER=1 \
    PYTHONUNBUFFERED=1

# /home/nexus/.cache is a named-volume mount target in compose (the
# fastembed/huggingface model cache). A named volume only inherits the
# image's ownership if the directory already exists in the image — without
# this line Docker creates the mount point root-owned and the first model
# download fails with "Permission denied" (same lesson as the unified image).
RUN mkdir -p /home/nexus/.cache && chown -R nexus:nexus /home/nexus/.cache

USER nexus
EXPOSE 8000
CMD ["uvicorn", "fastapi_app.main:app", "--host", "0.0.0.0", "--port", "8000"]
