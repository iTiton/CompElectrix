#!/bin/sh
# Punto de entrada: deja la carpeta de datos a nombre del usuario de la aplicación
# (Docker la crea como root si no existía) y continúa sin privilegios.
set -e
if [ "$(id -u)" = "0" ]; then
  chown -R compelectrix:compelectrix /data
  exec setpriv --reuid=compelectrix --regid=compelectrix --init-groups "$@"
fi
exec "$@"
