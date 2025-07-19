echo "Initiate PostgreSQl Database Schema and System Assets"
docker compose run --rm -e INSTALL_TB=true -e LOAD_DEMO=true thingsboard-ce
docker model pull ai/gemma3n:4B-Q4_K_M
