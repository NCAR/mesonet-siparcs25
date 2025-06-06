echo "Starting Services"
# docker-compose up -d && docker compose logs -f thingsboard-ce
docker-compose --profile default up -d
