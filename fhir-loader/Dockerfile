FROM mcr.microsoft.com/azurelinux/base/python:3.12@sha256:b006d366ab67c2170e5ed5b7d34500e0291373df7faedc1d1ca2472944f6c7b2

# Azure Linux uses python3, create symlink for compatibility
RUN ln -sf /usr/bin/python3 /usr/bin/python

WORKDIR /app

# Install dependencies
# Networks that block files.pythonhosted.org can pass --build-arg PIP_INDEX_URL=<index>.
ARG PIP_INDEX_URL=https://pypi.org/simple
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
