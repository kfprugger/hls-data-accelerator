FROM mcr.microsoft.com/cbl-mariner/base/python:3@sha256:d1dd9c1296ec1a311efc2dd35d74a9c8f2be3c5e264d9a26c847b1123807312c

# CBL-Mariner uses python3, create symlink for compatibility
RUN ln -sf /usr/bin/python3 /usr/bin/python

WORKDIR /app

# Install dependencies
COPY requirements.lock .
RUN pip install --no-cache-dir --require-hashes -r requirements.lock

# Copy application files
COPY load_fhir.py .
COPY device_registry.json .
COPY atlanta_providers.json .

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV FHIR_SERVICE_URL=""
ENV SYNTHEA_OUTPUT_PATH="/synthea-output/fhir"
ENV DEVICE_COUNT="100"

CMD ["python", "-u", "load_fhir.py"]
