# Use the base image image
FROM iotwx-base:latest

# Install compatible versions
RUN pip install --no-cache-dir "paho-mqtt==1.6.1"

# Copy the necessary files
COPY . ./services/mqtt_legacy/

WORKDIR /cloud/services/mqtt_legacy

# Run the scripts
CMD ["python3", "main.py"]
