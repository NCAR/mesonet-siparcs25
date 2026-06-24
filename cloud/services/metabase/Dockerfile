FROM python:3.11-slim

RUN pip install --no-cache-dir requests redis pyyaml flask uvicorn fastapi pydantic httpx python-dotenv psycopg2-binary "pydantic[email]"

COPY . /cloud/services/metabase/

WORKDIR /cloud/services/metabase

CMD python3 main.py && uvicorn api:app --host 0.0.0.0 --port 8001