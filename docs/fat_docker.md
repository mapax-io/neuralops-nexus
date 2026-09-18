# Self-host quick reference (unified image — see SELF-HOST.md for full steps)

# Get files
mkdir neuralops-selfhost && cd neuralops-selfhost
curl -fsSL https://raw.githubusercontent.com/mapax-io/neuralops-nexus/dev/docker-compose.neuralops.yaml -o docker-compose.neuralops.yaml
mkdir -p neuralops
curl -fsSL https://raw.githubusercontent.com/mapax-io/neuralops-nexus/dev/neuralops/infra.env.example -o neuralops/infra.env
curl -fsSL https://raw.githubusercontent.com/mapax-io/neuralops-nexus/dev/neuralops/app.env.example -o neuralops/app.env

# Generate per-deployment secrets (once, ever)
docker run --rm noamanfaisal/neuralops:0.2.0 init-secrets > neuralops/secrets.env

# Fill in neuralops/infra.env (POSTGRES_PASSWORD) and neuralops/app.env (NEURALOPS_SERVER_URL), then:
ENVF="--env-file neuralops/infra.env --env-file neuralops/app.env --env-file neuralops/secrets.env"
docker compose -f docker-compose.neuralops.yaml $ENVF up -d

# Django setup (through entrypoint.sh — venv isn't on the image's default PATH)
docker compose -f docker-compose.neuralops.yaml $ENVF exec nucleus entrypoint.sh nucleus-env python manage.py migrate
docker compose -f docker-compose.neuralops.yaml $ENVF exec nucleus entrypoint.sh nucleus-env python manage.py seed_permissions
docker compose -f docker-compose.neuralops.yaml $ENVF exec -it nucleus entrypoint.sh nucleus-env python manage.py create_owner

# Install Tailscale (skip if already installed)
curl -fsSL https://tailscale.com/install.sh | sh

# Start Tailscale
sudo tailscale up

# Enable Funnel on the nginx host port (default 8095)
sudo tailscale funnel --bg 8095

# After setting NEURALOPS_SERVER_URL in neuralops/app.env to the funnel URL:
docker compose -f docker-compose.neuralops.yaml $ENVF restart nucleus centrifugo

# Check containers / logs
docker compose -f docker-compose.neuralops.yaml $ENVF ps
docker compose -f docker-compose.neuralops.yaml $ENVF logs -f nucleus

---

## Superseded — old "fat" profile (docker-compose.yaml, multi-image), kept for reference

curl -fsSL https://raw.githubusercontent.com/mapax-io/neuralops-nexus/dev/install.sh | bash

docker compose exec nucleus-fat python manage.py migrate
docker compose exec nucleus-fat python manage.py seed_permissions
docker compose exec nucleus-fat python manage.py create_owner

curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
sudo tailscale funnel --bg 8090

docker inspect fat-nexus-ai --format '{{json .NetworkSettings.Networks}}'
docker inspect filesystem-mcp --format '{{json .NetworkSettings.Networks}}'
docker network connect fat-network filesystem-mcp
