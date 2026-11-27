FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ALGORE_HOST=0.0.0.0 \
    ALGORE_PORT=8000 \
    ALGORE_DB_PATH=/data/algore.db

WORKDIR /app
COPY engine/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY engine/app /app/app

RUN mkdir -p /data
VOLUME ["/data"]
EXPOSE 8000

CMD ["python", "-m", "app"]
