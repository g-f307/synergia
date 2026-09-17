# Relatório de baseline de desempenho

- Execução: `rupture-pg16-1280m-20260917-v00`
- Comparabilidade: `non_comparable`
- Ambiente: `perf-staircase-pg16-cgroup`
- Commit: `f4bd4284cca0357a5daa9b4b20454a314fa45426`
- Massa: `87abc303a2f4b4a211ab5a1f587a48e498516d27c6b8d30b48eb7e35327e8f6d`
- Erros inesperados: `0`
- Validações funcionais: `40/40`

## Resultados

| Operação | Rota | N | p50 ms | p95 ms | p99 ms | Erros |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| EXPORT | GET /reports/version/export (oqc_summary/csv) | 5 | 59.24 | 76.21 | 76.21 | 0 |
| EXPORT | GET /reports/version/export (oqc_summary/json) | 5 | 41.96 | 53.53 | 53.53 | 0 |
| EXPORT | GET /reports/version/export (workorder_consolidated/csv) | 5 | 38.54 | 40.31 | 40.31 | 0 |
| EXPORT | GET /reports/version/export (workorder_consolidated/json) | 5 | 35.97 | 41.83 | 41.83 | 0 |
| PROCESS | GET /imports/{id}/pipeline-summary | 1 | 31.74 | 31.74 | 31.74 | 0 |
| QUERY | consolidated | 5 | 82.42 | 99.01 | 99.01 | 0 |
| QUERY | history-list | 5 | 33.00 | 39.27 | 39.27 | 0 |
| QUERY | indicators | 5 | 47.90 | 52.30 | 52.30 | 0 |
| QUERY | lot-detail | 5 | 37.48 | 53.67 | 53.67 | 0 |
| QUERY | pending-list | 5 | 37.78 | 45.87 | 45.87 | 0 |
| QUERY | search-workorder | 5 | 46.08 | 50.81 | 50.81 | 0 |
| QUERY | serial-detail | 5 | 28.24 | 34.78 | 34.78 | 0 |
| QUERY | workorder-detail | 5 | 41.66 | 53.64 | 53.64 | 0 |
| REPORT | POST /reports (oqc_summary) | 5 | 82.58 | 87.98 | 87.98 | 0 |
| REPORT | POST /reports (workorder_consolidated) | 5 | 68.96 | 92.56 | 92.56 | 0 |
| UPLOAD | POST /imports | 1 | 3756.11 | 3756.11 | 3756.11 | 0 |

Consulte os arquivos JSON e CSV deste diretório para os dados completos.
