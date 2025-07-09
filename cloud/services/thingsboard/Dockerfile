# Use the base image image
FROM iotwx-base:latest

# Copy the necessary files
COPY . ./services/thingsboard/

WORKDIR /cloud/services/thingsboard

# Run the scripts
CMD ["python3", "main.py"]
