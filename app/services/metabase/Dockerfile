# Use official Python image
FROM iotwx-base:latest

# Copy the necessary files
COPY . ./metabase/

WORKDIR /app/metabase

# Run the scripts
CMD ["python3", "main.py"]
