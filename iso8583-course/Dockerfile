FROM mcr.microsoft.com/devcontainers/base:ubuntu-24.04
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    build-essential cmake make ninja-build gdb git ca-certificates \
    libboost-dev libboost-system-dev libsqlite3-dev sqlite3 libssl-dev openssl \
    python3 python3-venv python3-pip pkg-config ncat netcat-openbsd curl jq xxd \
    && rm -rf /var/lib/apt/lists/*
RUN python3 -m venv /opt/iso8583-venv && /opt/iso8583-venv/bin/pip install --no-cache-dir pyiso8583
ENV PATH="/opt/iso8583-venv/bin:${PATH}"
WORKDIR /workspaces
COPY scripts/container-smoke-test.sh /home/vscode/smoke-test.sh
RUN chmod 755 /home/vscode/smoke-test.sh && chown vscode:vscode /home/vscode/smoke-test.sh
