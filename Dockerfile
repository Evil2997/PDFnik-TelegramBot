# syntax=docker/dockerfile:1.8

FROM python:3.13-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install --prefix=/install -r requirements.txt


FROM python:3.13-slim AS runtime

WORKDIR /app

COPY --from=builder /install /usr/local

COPY . .

ENV PYTHONUNBUFFERED=1

CMD ["python3", "main.py"]
