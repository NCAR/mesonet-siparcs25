# Use the base image image
FROM iotwx-base:latest

# Copy the necessary files
COPY . ./database/

WORKDIR /app/database

# Run the scripts
CMD ["python3", "main.py"]
