#!/bin/sh
set -e
PORT=${PORT:-8080}
echo "Starting gunicorn on 0.0.0.0:$PORT"
exec gunicorn \
    --config gunicorn.conf.py \
    --bind "0.0.0.0:$PORT" \
    --workers 1 \
    --threads 8 \
    --worker-class gthread \
    --worker-tmp-dir /dev/shm \
    --timeout 120 \
    --access-logfile - \
    --error-logfile - \
    run:app
