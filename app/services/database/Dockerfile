# Use the base image image
FROM iotwx-base:latest

# Copy the necessary files
COPY . ./services/database/

WORKDIR /app/services/database

# Run the scripts
CMD ["python3", "main.py"]
