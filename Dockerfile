FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -g 10001 vaja && useradd -u 10001 -g vaja -m vaja
COPY requirements.lock.txt .
RUN pip install --no-cache-dir -r requirements.lock.txt
COPY --chown=vaja:vaja app ./app
COPY --chown=vaja:vaja worker ./worker
COPY --chown=vaja:vaja scripts ./scripts
RUN mkdir -p /app/data && chown vaja:vaja /app/data
USER vaja
ENV PYTHONUNBUFFERED=1 DATA_DIR=/app/data MODEL_CACHE_DIR=/app/data/models
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
