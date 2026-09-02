FROM mcr.microsoft.com/cbl-mariner/base/python:3@sha256:d1dd9c1296ec1a311efc2dd35d74a9c8f2be3c5e264d9a26c847b1123807312c
# CBL-Mariner uses python3, create symlink for compatibility
RUN ln -sf /usr/bin/python3 /usr/bin/python
COPY requirements.lock .
RUN pip install --no-cache-dir --require-hashes -r requirements.lock
COPY . /app
WORKDIR /app
CMD ["python", "-u", "load_dicom.py"]
