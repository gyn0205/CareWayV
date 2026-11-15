FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY alembic.ini ./
COPY migration/ ./migration/
COPY app/ ./app/
