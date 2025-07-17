# Use the base image image
FROM iotwx-base:latest

RUN pip install --no-cache-dir "paho-mqtt==2.1.0"

# Copy the necessary files
COPY . ./services/mqtt_listener/

WORKDIR /cloud/services/mqtt_listener

# Run the scripts
CMD ["python3", "mqtt_client.py"]
