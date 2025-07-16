FROM hub.k8s.ucar.edu/mesonet/iotwx-base:latest

# Copy application code and config
COPY . /cloud/services/map_server/
WORKDIR /cloud/services/map_server
# Set environment variables for Gunicorn
ENV GUNICORN_WORKERS=1
ENV GUNICORN_TIMEOUT=120

# Create templates/ directory and copy templates
RUN mkdir -p /cloud/services/map_server/templates
COPY templates/ /cloud/services/map_server/templates/

# Expose dynamic port
ARG APP_PORT=5000
EXPOSE ${APP_PORT}

# Run Gunicorn with gevent, using environment variables
CMD gunicorn -w ${GUNICORN_WORKERS:-1} --timeout ${GUNICORN_TIMEOUT:-120} -b 0.0.0.0:$APP_PORT --worker-class ${GUNICORN_WORKER_CLASS:-geventwebsocket.gunicorn.workers.GeventWebSocketWorker} $APP_MODULE