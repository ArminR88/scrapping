# 1. Base Image: Use a specific Python image for smaller size and built-in tools
# This is much better than starting from a full 'ubuntu:latest'
FROM python:3.11-slim

# 2. Environment Variable: Set a necessary environment variable for Python
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

LABEL org.opencontainers.image.source="." \
      org.opencontainers.image.description="Lightweight Python scraping container"

# 3. Working Directory: Set the directory inside the container
WORKDIR /app

# 4. Copy Dependency File: Copy only the requirements first to leverage caching
# This assumes you have a 'requirements.txt' listing your scraping libraries.
COPY requirements.txt /app/

# 5. Install Python Libraries and Cleanup: Install system dependencies (e.g., needed for certain libraries)
# 'libpq-dev' and 'build-essential' are common needs, adjust as required.
# If you use a browser like Selenium, you will need to add those dependencies here.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends build-essential ca-certificates wget; \
    python -m pip install --upgrade pip setuptools wheel; \
    pip install --no-cache-dir -r requirements.txt; \
    apt-get purge -y --auto-remove build-essential; \
    rm -rf /var/lib/apt/lists/*

# 6. Create a non-root user and set ownership of app files
RUN groupadd -r app && useradd -r -g app -d /app -s /sbin/nologin app

# 7. Copy Project Code: Copy the rest of your local project code
# and set ownership to the non-root user
COPY --chown=app:app . /app

# 8. Switch to non-root user
USER app

# 9. Command: Define the default command to run your main scraping script
# Replace 'scraper.py' with the name of your main script.
CMD ["python", "scraper.py"]