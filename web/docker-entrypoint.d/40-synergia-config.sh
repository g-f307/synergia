#!/bin/sh
set -eu

# Generate the public runtime settings before nginx starts.
envsubst '${SYNERGIA_API_ORIGIN}' \
  < /opt/synergia/runtime-config.js.template \
  > /usr/share/nginx/html/runtime-config.js
