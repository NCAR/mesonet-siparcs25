# Check status
systemctl status lora-gateway

# View logs
journalctl -u lora-gateway -f

# Verify virtualenv
ls -la /home/ncar/mesonet-siparcs25/edge-servers/.venv