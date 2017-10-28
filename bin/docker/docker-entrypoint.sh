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
ls -latr /usr/src/game
ls -latr /usr/src/game/server/conf
echo ""
echo "Server Config"
cat /usr/src/game/server/conf/settings.py
echo ""

if [ -f /run/secrets/evennia/secret_settings.py ]; then
  ln -sf /run/secrets/evennia/secret_settings.py /usr/src/game/server/conf/secret_settings.py
  echo "Linked secret settings into place."
  ls -latr /usr/src/game/server/conf
fi

if [ "$1" = 'evennia' ]; then
  chown -R ${USER}:${USER} /usr/src/{evennia,game}
  su-exec ${USER} evennia migrate
  exec su-exec ${USER} "$@"
fi

exec "$@"
