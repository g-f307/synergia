#!/bin/sh
set -eu

envsubst '${SYNERGIA_API_ORIGIN}' \
  < /opt/synergia/runtime-config.js.template \
  > /usr/share/nginx/html/runtime-config.js
