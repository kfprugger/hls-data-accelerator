FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY requirements.txt /app/gateway/requirements.txt
RUN pip install --no-cache-dir -r /app/gateway/requirements.txt \
    && useradd --create-home --uid 10001 gateway
COPY --chown=gateway:gateway . /app/gateway
USER gateway
EXPOSE 8000
# The registry admission lock requires the approved single-replica, single-worker topology.
CMD ["uvicorn", "gateway.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-proxy-headers"]
