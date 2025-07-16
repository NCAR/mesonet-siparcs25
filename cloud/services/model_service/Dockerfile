# Use the base image image
FROM hub.k8s.ucar.edu/mesonet/iotwx-base:latest


RUN pip install openai==1.93.0
# Copy your application code
WORKDIR /app
COPY . /app


# Command to run your application
CMD ["python", "app.py"]