# ---- Build stage ----
FROM python:3.13-slim-bookworm AS build

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential gcc && \
    rm -rf /var/lib/apt/lists/*

COPY CTFNotifier_Discord_Bot_v2/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---- Final stage ----
FROM python:3.13-slim-bookworm AS final

WORKDIR /app

# Install gosu for dropping privileges in entrypoint
RUN apt-get update && \
    apt-get install -y --no-install-recommends gosu && \
    rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd --gid 1000 botgroup && \
    useradd --uid 1000 --gid 1000 --no-create-home --shell /bin/false bot

# Copy Python packages from build stage
COPY --from=build /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=build /usr/local/bin /usr/local/bin

# Copy application code
COPY CTFNotifier_Discord_Bot_v2/ .

# Create data directory and set ownership
RUN mkdir -p /app/data && chown -R bot:botgroup /app

# Copy entrypoint
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

VOLUME /app/data

ENTRYPOINT ["entrypoint.sh"]
CMD ["python", "main.py"]
