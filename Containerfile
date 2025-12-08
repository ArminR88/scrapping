FROM python:3.11-slim

# 1. Environment and Metadata
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    BRAVE_EXECUTABLE=/usr/bin/brave-browser \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    WDM_LOCAL=/tmp/.wdm \
    XDG_CACHE_HOME=/tmp/.cache

LABEL org.opencontainers.image.description="Selenium vs. Playwright Performance Test"

# 2. Working Directory
WORKDIR /app

# 3. Copy Requirements and Install Dependencies (Single Layer Optimization)
COPY requirements.txt /app/

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        wget \
        gnupg \
        apt-transport-https \
        libnss3 \
        libasound2 \
        libatk-bridge2.0-0 \
        libgtk-3-0; \
    # Add Brave APT repo and key (optional)
    wget -qO- https://brave-browser-apt-release.s3.brave.com/brave-core.asc | gpg --dearmor > /usr/share/keyrings/brave-browser-archive-keyring.gpg; \
    echo "deb [signed-by=/usr/share/keyrings/brave-browser-archive-keyring.gpg arch=amd64] https://brave-browser-apt-release.s3.brave.com/ stable main" > /etc/apt/sources.list.d/brave.list; \
    apt-get update; \
    apt-get install -y --no-install-recommends brave-browser; \
    # prepare shared playwright browsers folder and install python deps
    mkdir -p /ms-playwright /tmp/.wdm /tmp/.cache; \
    python -m pip install --upgrade pip setuptools wheel; \
    pip install --no-cache-dir -r requirements.txt; \
    # install Playwright browsers into PLAYWRIGHT_BROWSERS_PATH (ENV provides /ms-playwright)
    python -m playwright install --with-deps chromium firefox webkit; \
    # cleanup
    apt-get purge -y --auto-remove build-essential gnupg wget apt-transport-https; \
    rm -rf /var/lib/apt/lists/*

# 4. Security and Code Copy
RUN groupadd -r app && useradd -r -g app -d /app -s /sbin/nologin app

# copy project and set ownership
COPY --chown=app:app . /app

# ensure playwright browsers and temp wdm/cache dirs are owned by app and /app is writable
RUN chown -R app:app /app /ms-playwright /tmp/.wdm /tmp/.cache

USER app

# 5. Execution Command
CMD ["python", "comparison_selenium_playwright.py"]