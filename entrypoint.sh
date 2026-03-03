#!/bin/sh

# Fix ownership of the data volume (mounted as root by Docker daemon)
chown -R bot:botgroup /app/data

# Drop privileges and run as bot user
exec gosu bot "$@"
