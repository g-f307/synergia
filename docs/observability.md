# Observabilidade operacional

A issue #93 entrega uma base local e reproduzível: logs JSON, sondas HTTP,
métricas Prometheus, alertas preliminares e painel Grafana. A #94 acrescenta o
estado de recuperação, runbooks e retenção operacional. A plataforma
corporativa definitiva e SLOs permanecem para validação posterior.

## Contratos e segurança

| Rota | Acesso | Resultado |
| --- | --- | --- |
| `GET /health/live` | público | `200 alive`; não consulta dependências |
| `GET /health/ready` | público | `200 ready` ou `503 not_ready`; exige PostgreSQL e armazenamento |
| `GET /health` | público | estado completo; e-mail é dependência opcional e pode degradar |
| `GET /metrics` | Bearer técnico | exposição Prometheus; `401` sem credencial e `503` sem configuração segura |

As sondas retornam apenas componente, estado, criticidade, duração e código de
motivo. Nunca retornam DSN, caminho, exceção ou conteúdo operacional. Configure
`OBSERVABILITY_METRICS_TOKEN` com pelo menos 32 bytes e mantenha a rota restrita
à rede de monitoramento.

## Correlação e logs

Cada requisição recebe ou gera `X-Correlation-ID`. O mesmo UUID acompanha o log
operacional e, quando aplicável, `executions.correlation_id` e
`audit_events.correlation_id`; `execution_id` conecta eventos da jornada.
Auditoria continua persistida e imutável no banco, separada dos logs técnicos.

Logs aceitam somente campos estáveis da allowlist em
`app/observability/telemetry.py`. JWT, refresh token, senha, hashes de sujeito,
avatar, nome/caminho/conteúdo de arquivo, snapshot e corpo de relatório são
proibidos. Rotas de métricas usam templates, nunca URL ou query concreta.

## Métricas e cardinalidade

- `synergia_http_requests_total` e `synergia_http_request_duration_seconds`;
- `synergia_dependency_up` e `synergia_dependency_degraded`;
- `synergia_operational_records` e `synergia_operational_events_total`;
- `synergia_queue_depth` e `synergia_queue_oldest_age_seconds`;
- `synergia_operation_duration_seconds` e `synergia_import_rows_total`;
- `synergia_rate_limit_denials_total` e
  `synergia_observability_collection_success`;
- `synergia_data_operation_last_success_timestamp_seconds` e
  `synergia_data_operation_failures_total`.

Labels são limitadas a método, template de rota, classe HTTP, componente,
jornada, estado/outcome, fila, operação e dimensão predefinidos. IDs, e-mail,
organização, origem/IP e hashes não são labels.

## Execução local e alertas

Copie `observability/secrets.example/metrics-token` para o caminho ignorado
`observability/secrets/metrics-token`, use o mesmo valor em
`OBSERVABILITY_METRICS_TOKEN` no backend. Para o Prometheus em contêiner
alcançar a API local, inicie-a no ambiente controlado com:

```bash
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Na raiz, execute:

```bash
docker compose -f observability/compose.yml up -d
```

O Prometheus fica em `127.0.0.1:19090` e o Grafana em `127.0.0.1:13000`. Seu
volume possui retenção explícita de 15 dias e não integra o backup de dados. O painel
provisionado cobre disponibilidade, volume, latência, erros, rejeições,
processamento, relatórios, notificações/e-mail, aprovações, filas,
reprocessamento e bloqueios de limite.

As regras em `observability/prometheus/alerts.yml` detectam indisponibilidade
total da API pelo `up` do scrape, dependência crítica, coleta indisponível,
worker degradado, taxa HTTP 5xx, falhas das jornadas, rejeição elevada, filas
paradas, backlog de aprovação e bloqueios abusivos.
Limiares são iniciais, versionados e validados por `promtool`; não constituem
SLO. As regras também detectam backup ausente/atrasado e falhas persistidas de
backup, verificação e retenção. Falhas de restauração anteriores à existência
do banco alvo são emitidas pelo CLI somente como código e correlation ID seguros
e exigem abertura do incidente pelo operador. Todos os `runbook` apontam para procedimentos versionados em
[`runbooks/`](runbooks/backup-restore.md).

O `/health` inclui `data_recovery` como componente não crítico. Ausência,
atraso ou falha posterior ao último backup degrada a saúde completa, mas não
retira da rotação uma API cujo banco e storage continuam disponíveis. A
readiness permanece restrita às dependências necessárias para atender tráfego.

## Validação

```bash
cd backend && pytest -q -m "not integration" tests/test_health.py tests/test_observability.py
pytest -q -m integration tests/test_observability_persistence.py
docker run --rm --entrypoint promtool \
  -v "$PWD/../observability/prometheus:/etc/prometheus" \
  prom/prometheus:v3.14.0 test rules /etc/prometheus/alerts.test.yml
```
