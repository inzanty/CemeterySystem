#!/bin/sh
set -eu
mkdir -p "$MEDIA_ROOT" "$STATIC_ROOT"
python manage.py migrate --noinput
python manage.py collectstatic --noinput
exec "$@"
