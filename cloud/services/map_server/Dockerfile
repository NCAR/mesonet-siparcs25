FROM python:3.11-slim

RUN pip install --no-cache-dir flask flask-socketio pyyaml redis gevent gevent-websocket python-socketio python-engineio

COPY . /cloud/services/map_server/
WORKDIR /cloud/services/map_server

RUN mkdir -p /cloud/services/map_server/templates
COPY templates/ /cloud/services/map_server/templates/

ARG APP_PORT=5001
EXPOSE ${APP_PORT}

CMD ["python", "map_app.py"]
