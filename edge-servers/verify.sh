# Check status
systemctl status lora-gateway

# Verify virtualenv
ls -la /home/ncar/mesonet-siparcs25/edge-servers/.venv

# View logs
journalctl -u lora-gateway -f

