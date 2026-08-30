#!/usr/bin/env bash
set -euo pipefail

api_url="${API_URL:-http://localhost:8000}"
demo_dir="$(mktemp -d)"
trap 'rm -rf "$demo_dir"' EXIT

python scripts/generate_synthetic_data.py \
  --profile minimal --scenario valid --formats csv --output "$demo_dir"

response="$(curl --fail --silent --show-error \
  -F 'source=N-FP' -F "file=@${demo_dir}/n-fp.csv" \
  -F 'source=OWM' -F "file=@${demo_dir}/owm.csv" \
  -F 'source=GMES/OQC' -F "file=@${demo_dir}/gmes-oqc.csv" \
  -F 'source=TMS' -F "file=@${demo_dir}/tms.csv" \
  -F 'technical_origin=synthetic-monitoring-demo' \
  "${api_url}/imports")"
execution_id="$(python -c 'import json,sys; print(json.load(sys.stdin)["execution_id"])' \
  <<< "$response")"

printf 'Execução sintética criada: %s\n' "$execution_id"

curl --fail --silent --show-error "${api_url}/executions/${execution_id}"
curl --fail --silent --show-error \
  "${api_url}/executions/${execution_id}/divergences?page=1&page_size=20&sort=oldest"
curl --fail --silent --show-error \
  "${api_url}/executions/${execution_id}/classifications?page=1&page_size=20&sort=oldest"
curl --fail --silent --show-error \
  "${api_url}/executions/${execution_id}/pending-items?page=1&page_size=20&sort=oldest"
curl --fail --silent --show-error \
  "${api_url}/executions/${execution_id}/evidences?page=1&page_size=20&sort=oldest"
