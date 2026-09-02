FROM mcr.microsoft.com/cbl-mariner/base/python:3@sha256:d1dd9c1296ec1a311efc2dd35d74a9c8f2be3c5e264d9a26c847b1123807312c
ENV PYTHONUNBUFFERED=1
RUN ln -sf /usr/bin/python3 /usr/bin/python
COPY requirements.lock /app/requirements.lock
RUN pip install --no-cache-dir --require-hashes -r /app/requirements.lock
COPY claim_emulator.py /app/claim_emulator.py
WORKDIR /app
CMD ["python", "-u", "claim_emulator.py"]
