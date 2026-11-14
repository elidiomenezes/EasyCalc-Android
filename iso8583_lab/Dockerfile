FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Match the ISO8583 course toolchain: C/C++ build tools, debugging utilities,
# Boost.Asio/Boost.System, OpenSSL and SQLite development headers and libraries.
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    build-essential cmake make ninja-build gdb git ca-certificates \
    libboost-dev libboost-system-dev libsqlite3-dev sqlite3 libssl-dev openssl \
    pkg-config ncat netcat-openbsd curl jq xxd \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN python3 -m pip install --no-cache-dir -r requirements.txt

COPY . ./
COPY docker_root_smoke.sh /root/smoke-test.sh
RUN chmod 755 /root/smoke-test.sh

EXPOSE 8500-8599

CMD ["/bin/bash"]
