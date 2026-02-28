FROM python:3.13-slim-bookworm AS build
WORKDIR /src/

# Install GCC for aiohttp build
RUN apt-get update &&\
    apt-get install -y --no-install-recommends build-essential gcc

# Build & activate venv
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -Ur requirements.txt

# 2 stage build, reuse venv
FROM python:3.13-slim-bookworm AS final

# Create group and user  for bot files
RUN addgroup --gid 1000 --system botgroup &&\
    adduser --uid 1000 --gid 1000 --disabled-password --gecos "" bot

WORKDIR /src/

# Reuse Venv
COPY --from=build --chown=bot:botgroup /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy files and set ownership
ADD CTFNotifier_Discord_Bot_v2 .
RUN mkdir -p data

# Add entrypoint
COPY entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/entrypoint.sh

# Set user and access
RUN chown -R bot:botgroup .
USER bot

# Volume for data persistence
VOLUME /app/data

ENTRYPOINT ["entrypoint.sh"]
CMD ["python", "main.py"]