echo "Initiate PostgreSQl Database Schema and System Assets"
docker compose run --rm -e INSTALL_TB=true -e LOAD_DEMO=true thingsboard-ce
