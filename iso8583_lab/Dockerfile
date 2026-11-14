FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt ./
RUN python3 -m pip install --no-cache-dir -r requirements.txt

COPY . ./
COPY docker_root_smoke.sh /root/smoke-test.sh
RUN chmod 755 /root/smoke-test.sh

EXPOSE 8500-8599

CMD ["/bin/bash"]
