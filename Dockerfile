FROM python:3.15.0a6-slim-bookworm AS compile-image
WORKDIR /app/

# Install GCC for aiohttp build
RUN apt-get update
RUN apt-get -y install --no-install-recommends build-essential gcc mono-mcs
RUN rm -rf /var/lib/apt/lists/*

# Build & activate venv
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install requirements
COPY requirements.txt .
RUN pip install -Ur requirements.txt

# 2 stage build, reuse venv
FROM python:3.15.0a6-slim-bookworm AS build-image

# Create group and user  for bot files
RUN addgroup --system botgroup && adduser --system --ingroup botgroup bot

WORKDIR /app/

# Reuse Venv
COPY --from=compile-image --chown=bot:botgroup /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy files and set ownership
COPY . /app

# Set user and access
RUN chown -R bot:botgroup /app
USER bot

# Volume for data persistence
VOLUME /app/data
CMD ["python", "main.py"]