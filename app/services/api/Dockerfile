# Use the base image image
FROM iotwx-base:latest

# Copy the necessary files
COPY . ./services/api/

WORKDIR /app/services/api

# Run the scripts
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
