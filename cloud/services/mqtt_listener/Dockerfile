FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y gcc libffi-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "paho-mqtt==2.1.0" requests redis pyyaml "pydantic[email]"

COPY . /app/

WORKDIR /app

CMD ["python3", "mqtt_client.py"]