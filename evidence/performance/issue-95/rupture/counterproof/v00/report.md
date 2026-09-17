# Relatório de baseline de desempenho

- Execução: `rupture-pg16-reallocated-20260917-v00`
- Comparabilidade: `non_comparable`
- Ambiente: `perf-staircase-pg16-reallocated`
- Commit: `f4bd4284cca0357a5daa9b4b20454a314fa45426`
- Massa: `87abc303a2f4b4a211ab5a1f587a48e498516d27c6b8d30b48eb7e35327e8f6d`
- Erros inesperados: `0`
- Validações funcionais: `40/40`

## Resultados

| Operação | Rota | N | p50 ms | p95 ms | p99 ms | Erros |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| EXPORT | GET /reports/version/export (oqc_summary/csv) | 5 | 60.27 | 64.86 | 64.86 | 0 |
| EXPORT | GET /reports/version/export (oqc_summary/json) | 5 | 54.78 | 57.46 | 57.46 | 0 |
| EXPORT | GET /reports/version/export (workorder_consolidated/csv) | 5 | 33.33 | 49.25 | 49.25 | 0 |
| EXPORT | GET /reports/version/export (workorder_consolidated/json) | 5 | 39.44 | 45.33 | 45.33 | 0 |
| PROCESS | GET /imports/{id}/pipeline-summary | 1 | 50.03 | 50.03 | 50.03 | 0 |
| QUERY | consolidated | 5 | 73.92 | 85.01 | 85.01 | 0 |
| QUERY | history-list | 5 | 32.40 | 38.50 | 38.50 | 0 |
| QUERY | indicators | 5 | 39.24 | 49.46 | 49.46 | 0 |
| QUERY | lot-detail | 5 | 46.51 | 50.92 | 50.92 | 0 |
| QUERY | pending-list | 5 | 36.87 | 46.84 | 46.84 | 0 |
| QUERY | search-workorder | 5 | 38.20 | 46.69 | 46.69 | 0 |
| QUERY | serial-detail | 5 | 36.14 | 40.94 | 40.94 | 0 |
| QUERY | workorder-detail | 5 | 40.96 | 48.87 | 48.87 | 0 |
| REPORT | POST /reports (oqc_summary) | 5 | 76.35 | 79.85 | 79.85 | 0 |
| REPORT | POST /reports (workorder_consolidated) | 5 | 70.24 | 77.73 | 77.73 | 0 |
| UPLOAD | POST /imports | 1 | 4596.39 | 4596.39 | 4596.39 | 0 |

Consulte os arquivos JSON e CSV deste diretório para os dados completos.
