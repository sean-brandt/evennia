#!/bin/bash
set -e

echo "Environment:"
env
echo ""

if [ "$1" = 'evennia' ]; then
  chown -R ${USER}:${USER} /usr/src/{evennia,game}
  su-exec ${USER} evennia migrate
  exec su-exec ${USER} "$@"
fi

exec "$@"
