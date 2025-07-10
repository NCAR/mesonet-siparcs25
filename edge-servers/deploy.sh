# Make script executable
chmod +x /home/ncar/mesonet-siparcs25/edge-servers/setup_and_run.sh

# Install service
sudo systemctl daemon-reload
sudo systemctl enable lora-gateway
sudo systemctl start lora-gateway