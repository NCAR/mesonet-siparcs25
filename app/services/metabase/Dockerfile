# Use official Python image
FROM iotwx-base:latest

# Copy the necessary files
COPY . ./services/metabase/

WORKDIR /app/services/metabase

# Run the scripts
CMD ["python3", "main.py"]
