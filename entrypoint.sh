#!/bin/bash

until nc -z "${DB_HOST}" "${DB_PORT}"; do
  echo "Waiting for PostgreSQL to be reachable..."
  sleep 5
done

echo "PostgreSQL is reachable!"


cd backend && \
alembic upgrade head && \
cd ..

TOKEN=$(cat /var/run/secrets/kubernetes.io/serviceaccount/token) \
uvicorn backend.main:app --host 0.0.0.0 --port 8000
