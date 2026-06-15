FROM python:3.11-slim

RUN apt-get update && apt-get install -y gcc libffi-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uvicorn fastapi psycopg2-binary "pydantic[email]" sqlalchemy asyncpg email-validator

COPY . /app/

WORKDIR /app

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
