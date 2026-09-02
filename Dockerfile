FROM mcr.microsoft.com/cbl-mariner/base/python:3@sha256:d1dd9c1296ec1a311efc2dd35d74a9c8f2be3c5e264d9a26c847b1123807312c
ENV PYTHONUNBUFFERED=1
RUN ln -sf /usr/bin/python3 /usr/bin/python
COPY emulator-requirements.lock /app/emulator-requirements.lock
RUN pip install --no-cache-dir --require-hashes -r /app/emulator-requirements.lock
COPY emulator.py /app/emulator.py
WORKDIR /app
CMD ["python", "-u", "emulator.py"]
