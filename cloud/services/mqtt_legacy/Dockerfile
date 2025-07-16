# Use the base image image
FROM hub.k8s.ucar.edu/mesonet/iotwx-base:latest

# Copy the necessary files
COPY . ./services/mqtt_legacy/

WORKDIR /cloud/services/mqtt_legacy

# Run the scripts
CMD ["python3", "main.py"]
