#!/bin/bash

echo "Environment:"
env
echo ""

echo "Network Info:"
ip addr
echo ""
echo ""
netstat -an |grep LIST
echo ""
echo ""
echo "Filesystem Info"
ls -latr /
ls -latrR /run

set -e

if [ "$1" = 'evennia' ]; then
  chown -R ${USER}:${USER} /usr/src/{evennia,game}
  su-exec ${USER} evennia migrate
  exec su-exec ${USER} "$@"
fi

exec "$@"
