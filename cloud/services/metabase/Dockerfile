# Use official Python image
FROM hub.k8s.ucar.edu/mesonet/iotwx-base:latest

# Copy the necessary files
COPY . ./services/metabase/

WORKDIR /cloud/services/metabase

# Run the scripts
CMD python3 main.py && uvicorn api:app --host 0.0.0.0 --port 8001
