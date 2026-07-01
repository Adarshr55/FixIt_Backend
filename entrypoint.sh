#!/bin/bash
# entrypoint.sh — runs before any container command

set -e

echo "========================================"
echo " FixIt Backend — Starting up"
echo "========================================"

# ── Wait for PostgreSQL ───────────────────────────────────────────────────────
echo "Waiting for PostgreSQL..."
until python -c "
import psycopg2, os, sys
try:
    psycopg2.connect(
        host=os.environ.get('DB_HOST', 'db'),
        port=os.environ.get('DB_PORT', '5432'),
        dbname=os.environ.get('DB_NAME', 'fixit_db'),
        user=os.environ.get('DB_USER', 'fixit_user'),
        password=os.environ.get('DB_PASSWORD', ''),
    )
    sys.exit(0)
except Exception:
    sys.exit(1)
"; do
    echo "  PostgreSQL not ready — retrying in 2s..."
    sleep 2
done
echo "PostgreSQL is ready."


# ── Wait for Redis ────────────────────────────────────────────────────────────
echo "Waiting for Redis..."
until python -c "
import redis, os, sys
try:
    r = redis.Redis(
        host=os.environ.get('REDIS_HOST', 'redis'),
        port=int(os.environ.get('REDIS_PORT', '6379')),
        socket_connect_timeout=2,
    )
    r.ping()
    sys.exit(0)
except Exception:
    sys.exit(1)
"; do
    echo "  Redis not ready — retrying in 2s..."
    sleep 2
done
echo "Redis is ready."


# ── Only the web container runs migrations ────────────────────────────────────
if [ "$SKIP_MIGRATIONS" != "true" ]; then

    echo "Running migrations..."
    python manage.py migrate --noinput

    echo "Ensuring pgvector extension exists..."
    python manage.py shell -c "
from django.db import connection
with connection.cursor() as cursor:
    cursor.execute('CREATE EXTENSION IF NOT EXISTS vector;')
print('pgvector ready.')
"

    echo "Seeding vector embeddings for categories..."
    python manage.py seed_embeddings --type categories \
        || echo "WARNING: Seeding failed — run manually: python manage.py seed_embeddings"

    echo "Collecting static files..."
    python manage.py collectstatic --noinput --clear

    # ── Optional: create admin superuser on first deploy ─────────────────
    if [ "$CREATE_SUPERUSER" = "true" ] && \
       [ -n "$ADMIN_EMAIL" ] && \
       [ -n "$ADMIN_PASSWORD" ]; then
        echo "Creating platform admin user..."
        python manage.py shell -c "
from accounts.models import User
if not User.objects.filter(email='$ADMIN_EMAIL').exists():
    User.objects.create_platform_admin(
        email='$ADMIN_EMAIL',
        password='$ADMIN_PASSWORD',
    )
    print('Admin user created: $ADMIN_EMAIL')
else:
    print('Admin user already exists: $ADMIN_EMAIL')
"
    fi

fi

echo "Starting: $@"
echo "========================================"

exec "$@"