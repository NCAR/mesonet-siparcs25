FROM python:3.11-slim

RUN apt-get update && apt-get install -y gcc libffi-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir flask numpy scikit-learn requests openai

COPY . /app/

WORKDIR /app

CMD ["python3", "app.py"]
