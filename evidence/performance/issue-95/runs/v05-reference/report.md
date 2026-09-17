# Relatório de baseline de desempenho

- Execução: `v05-org001-reconciled-pg16-20260917`
- Comparabilidade: `non_comparable`
- Ambiente: `perf-isolated-pg16`
- Commit: `f4bd4284cca0357a5daa9b4b20454a314fa45426`
- Massa: `e8aac580f62c91a11a199a44a4daca8c40f498fc4cb7f9fdbda1af40cd0aa059`
- Erros inesperados: `0`
- Validações funcionais: `39/39`

## Resultados

| Operação | Rota | N | p50 ms | p95 ms | p99 ms | Erros |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| EXPORT | GET /reports/version/export (oqc_summary/csv) | 1 | 3150.74 | 3150.74 | 3150.74 | 0 |
| EXPORT | GET /reports/version/export (oqc_summary/json) | 1 | 1529.12 | 1529.12 | 1529.12 | 0 |
| EXPORT | GET /reports/version/export (workorder_consolidated/csv) | 1 | 253.17 | 253.17 | 253.17 | 0 |
| EXPORT | GET /reports/version/export (workorder_consolidated/json) | 1 | 165.87 | 165.87 | 165.87 | 0 |
| PROCESS | GET /executions/{id} | 1 | 100.21 | 100.21 | 100.21 | 0 |
| PROCESS | GET /imports/{id}/pipeline-summary | 1 | 41.33 | 41.33 | 41.33 | 0 |
| QUERY | consolidated | 1 | 112.79 | 112.79 | 112.79 | 0 |
| QUERY | history-list | 1 | 50.35 | 50.35 | 50.35 | 0 |
| QUERY | indicators | 1 | 48.31 | 48.31 | 48.31 | 0 |
| QUERY | lot-detail | 1 | 48.92 | 48.92 | 48.92 | 0 |
| QUERY | pending-list | 1 | 34.14 | 34.14 | 34.14 | 0 |
| QUERY | search-workorder | 1 | 84.80 | 84.80 | 84.80 | 0 |
| QUERY | serial-detail | 1 | 22.86 | 22.86 | 22.86 | 0 |
| QUERY | workorder-detail | 1 | 42.35 | 42.35 | 42.35 | 0 |
| REPORT | POST /reports (oqc_summary) | 1 | 2662.42 | 2662.42 | 2662.42 | 0 |
| REPORT | POST /reports (workorder_consolidated) | 1 | 447.04 | 447.04 | 447.04 | 0 |

Consulte os arquivos JSON e CSV deste diretório para os dados completos.
