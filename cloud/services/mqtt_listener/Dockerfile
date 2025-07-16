# Use the base image image
FROM hub.k8s.ucar.edu/mesonet/iotwx-base:latest

# Copy the necessary files
COPY . ./services/mqtt_listener/

WORKDIR /cloud/services/mqtt_listener

# Run the scripts
CMD ["python3", "mqtt_client.py"]
