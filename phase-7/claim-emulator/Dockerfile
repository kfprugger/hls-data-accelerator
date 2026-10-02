FROM mcr.microsoft.com/azurelinux/base/python:3.12@sha256:b006d366ab67c2170e5ed5b7d34500e0291373df7faedc1d1ca2472944f6c7b2
ENV PYTHONUNBUFFERED=1
RUN ln -sf /usr/bin/python3 /usr/bin/python
# Networks that block files.pythonhosted.org can pass --build-arg PIP_INDEX_URL=<index>.
ARG PIP_INDEX_URL=https://pypi.org/simple
COPY requirements.lock /app/requirements.lock
RUN pip install --no-cache-dir --require-hashes -r /app/requirements.lock
COPY claim_emulator.py /app/claim_emulator.py
WORKDIR /app
CMD ["python", "-u", "claim_emulator.py"]
