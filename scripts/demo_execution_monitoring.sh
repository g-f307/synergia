#!/usr/bin/env bash
set -euo pipefail

api_url="${API_URL:-http://localhost:8000}"
execution_id="${EXECUTION_ID:?Defina EXECUTION_ID com uma execução sintética persistida}"

curl --fail --silent --show-error "${api_url}/executions/${execution_id}"
curl --fail --silent --show-error \
  "${api_url}/executions/${execution_id}/divergences?page=1&page_size=20&sort=oldest"
curl --fail --silent --show-error \
  "${api_url}/executions/${execution_id}/classifications"
curl --fail --silent --show-error \
  "${api_url}/executions/${execution_id}/pending-items"
curl --fail --silent --show-error \
  "${api_url}/executions/${execution_id}/evidences"
