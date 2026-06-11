# Dockerfile — Virtual Sandbox Desktop with MCP + Control API
FROM mambaorg/micromamba:1.5.8

USER root
SHELL ["/bin/bash", "-lc"]

# Put conda python first
ENV PATH=/opt/conda/bin:${PATH}
ENV MAMBA_NO_BANNER=1
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright-browsers
ENV PIP_NO_CACHE_DIR=1

# System deps for X, VNC, Chromium
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    xvfb fluxbox xterm tmux xauth x11-apps \
    x11vnc novnc websockify x11-utils x11-xserver-utils \
    libglib2.0-0 libnss3 libnspr4 libdrm2 libgbm1 libxkbcommon0 libxcomposite1 \
    libxrandr2 libxdamage1 libxfixes3 libxi6 libxrender1 libxshmfence1 \
    libxext6 libx11-xcb1 libxcb1 libxcb-dri3-0 \
    libgtk-3-0 libatk-bridge2.0-0 libatspi2.0-0 libpango-1.0-0 libpangocairo-1.0-0 \
    libcups2 libasound2 fonts-dejavu fontconfig ca-certificates curl tini \
    sudo vim openssh-server git \
    at-spi2-core python3-gi python3-pyatspi python3-dbus dbus-x11 gir1.2-atspi-2.0 \
    tesseract-ocr tesseract-ocr-eng wmctrl xdotool \
    gnome-screenshot scrot imagemagick \
    ripgrep sed tree \
    build-essential gcc g++ make \
    # Build tools for compiling Python C extensions (torch-scatter, etc.)
 && rm -rf /var/lib/apt/lists/*
  

# Python toolchain via micromamba
ARG PYTHON_VERSION=3.12
RUN micromamba install -y -p /opt/conda -c conda-forge python=${PYTHON_VERSION} pip \
 && micromamba clean --all -y

# Python deps (pip into /opt/conda)
RUN python -m pip install --upgrade pip \
 && pip install --no-cache-dir fastapi uvicorn httpx pydantic playwright websockets beautifulsoup4 PyPDF2

# Install Playwright system dependencies first
RUN playwright install-deps chromium

# Pre-download Playwright Chromium and make sure chromium is in PATH
RUN python -m playwright install chromium
RUN CHROMIUM_PATH=$(python -c "from playwright.sync_api import sync_playwright; p=sync_playwright().start(); print(p.chromium.executable_path); p.stop()") && \
    echo "Chromium installed at: $CHROMIUM_PATH" && \
    ln -s "$CHROMIUM_PATH" /usr/local/bin/chromium && \
    ls -l /usr/local/bin/chromium

# Create agent user with sudo privileges
RUN useradd -ms /bin/bash agent && \
    echo 'agent:passw0rd' | chpasswd && \
    echo 'agent ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/agent && \
    mkdir -p /home/agent/.ssh && \
    chmod 700 /home/agent/.ssh && \
    chown -R agent:agent /home/agent/.ssh 

RUN mkdir /var/run/sshd
# Disable root login
RUN usermod -s /usr/sbin/nologin root
RUN sed -i 's/^PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config && \
    echo 'AllowUsers agent' >> /etc/ssh/sshd_config


# Shared workspace
RUN mkdir -p /workspace && chown -R agent:agent /workspace
RUN chown -R agent:agent /opt/conda
RUN mkdir -p /opt/conda/envs && chown -R agent:agent /opt/conda/envs

# Create directory for external tools
RUN mkdir -p /opt/tools && chown -R agent:agent /opt/tools

# Install vm package
ARG VM_PACKAGE=sandbox_vm
ENV VM_PACKAGE=${VM_PACKAGE}
WORKDIR /home/agent/app/src

COPY ./src .
RUN pip install -r ${VM_PACKAGE}/requirements.txt 

RUN chown -R agent:agent /home/agent

# Switch to agent
USER agent
ENV HOME=/home/agent
ENV PATH=/opt/conda/bin:${PATH}


# Entrypoint
ENTRYPOINT ["/usr/bin/tini", "-s", "--"]
CMD ["sh", "-c", "bash /home/agent/app/src/${VM_PACKAGE}/start.sh"]
