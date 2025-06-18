# Use the base image image
FROM iotwx-base:latest

# Copy the necessary files
COPY . ./services/database_api/

WORKDIR /cloud/services/database_api/

# Run the scripts
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
