FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    NOTEMELD_CLOUD_DATA_DIR=/var/lib/notemeld-cloud

WORKDIR /app
COPY cloud/requirements.txt /app/cloud/requirements.txt
RUN pip install --no-cache-dir -r /app/cloud/requirements.txt \
    && useradd --create-home --uid 10001 notemeld \
    && mkdir -p /var/lib/notemeld-cloud \
    && chown -R notemeld:notemeld /var/lib/notemeld-cloud

COPY cloud /app/cloud
USER notemeld

EXPOSE 8583
CMD ["uvicorn", "cloud.main:app", "--host", "0.0.0.0", "--port", "8583"]
