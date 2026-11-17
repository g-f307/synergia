# Observabilidade da assistência — contrato 1.0.0

Entrega incremental da #191. Os blocos 1–3 cobrem controles, fronteiras,
rotinas finitas, alertas e painel. O bloco 4 completa a campanha adversarial e
o exercício Graylog em laboratório sintético; a ativação operacional depende da #192.

## O que cada contagem significa

- **HTTP:** cada POST concluído é contado uma vez. Reutilização é uma solicitação,
  mas não uma inferência. O timeout HTTP não é reclassificado se o worker terminar
  depois. GET de leitura, capability e sonda não entram nessa contagem.
- **Gerador/provider:** mede o trabalho interno, mesmo quando o cliente já não
  está esperando. Um contexto insuficiente não cria amostra de inferência.
- **Persistência:** eventos e reservas descrevem o que foi confirmado no banco.
  A conclusão persistida pode acontecer após o timeout HTTP. Não somar contadores
  dessas três visões como se fossem solicitações independentes.

Denegações 401/403/404/409/422/429, cancelamento de cliente e flags desligadas são
separadas dos seis resultados de atendimento. Uma flag desligada não entra no
denominador da disponibilidade do runtime. A classificação `unavailable` também
inclui falhas de contexto/persistência; usar os códigos e as métricas por fronteira
para distinguir a dependência envolvida, sem atribuir toda falha ao modelo.

## Famílias de métricas

Prefixo de todas as famílias abaixo: `synergia_ai_assistance_`.

| Sufixo | Tipo | Significado |
| --- | --- | --- |
| `requests_total` | Counter | Resultado HTTP: generated, reused, insufficient, rejected, unavailable ou timeout |
| `request_denials_total` | Counter | Recusa de admissão, por código fechado; fora da taxa de indisponibilidade |
| `response_origins_total` | Counter | Origem model/deterministic efetivamente entregue em POST 200 |
| `context_seconds` | Histogram | Montagem do contexto, inclusive leitura e falhas |
| `inference_seconds` | Histogram | Chamada ao provider, incluindo verificação de pin/transporte e falhas; não mede só tempo de GPU |
| `generation_seconds` | Histogram | Gerador, incluindo validação/fallback |
| `total_seconds` | Histogram | POST completo, incluindo autenticação, admissão e erro; diferente do timing interno do contrato público |
| `context_bytes` | Histogram | Tamanho UTF-8 do snapshot serializado validado |
| `response_bytes` | Histogram | Bytes do conteúdo do modelo recebido antes da validação JSON |
| `generations_in_progress` | Gauge | Chamadas ao provider ainda em execução, mesmo após timeout/cancelamento HTTP |
| `generations_total` | Counter | Resultado interno do gerador, origem e código de rejeição |
| `contexts_total` | Counter | Contextos montados, por suficiência |
| `context_truncations_total` | Counter | Seções truncadas, por código fechado |
| `persistence_total` | Counter | Resultado das operações do repositório, após finalizar a transação |
| `security_rejections_total` | Counter | Integridade da resposta persistida no POST e tentativa de escopo confirmada internamente |
| `enabled`, `generation_enabled` | Gauge | Flags efetivas, sem endpoint, modelo ou segredo |
| `collection_success` | Gauge | 1 quando a leitura dos agregados persistidos foi possível; 0 significa ausência de medição, não ausência de falhas |
| `pending_reservations` | Gauge | Reservas processing, inclusive expiradas; não representa uma nova fila de inferência |
| `expired_reservations` | Gauge | Reservas processing cujo prazo venceu |
| `oldest_reservation_age_seconds` | Gauge | Idade da reserva processing mais antiga |
| `reservations_recovered_total` | Counter persistido | Reservas processing removidas com evento expired, por recuperação explícita/automática ou retenção |
| `persisted_integrity_errors_total` | Counter persistido | Falhas de integridade registradas na leitura do repositório |
| `persisted_completions_total` | Counter persistido | Eventos completed/rejected; inclui encerramento por falha do provider, sem confundir com entrega HTTP |
| `last_completion_timestamp_seconds` | Gauge persistido | Instante da última conclusão completed/rejected; zero se nunca houve, sem contar reserva ou remoção por expiração |
| `retention_runs_total`, `recovery_runs_total` | Counter persistido | Rotinas efetivas por transição started/succeeded/failed; prévias excluídas |
| `retention_removed_records_total`, `recovery_removed_records_total` | Counter persistido | Registros removidos por lotes de worker confirmados |
| `retention_last_started_timestamp_seconds` e equivalentes `recovery_…` | Gauge persistido | Último início confirmado |
| `retention_last_success_timestamp_seconds` e equivalentes `recovery_…` | Gauge persistido | Último sucesso, inclusive lote vazio |
| `retention_last_failure_timestamp_seconds` e equivalentes `recovery_…` | Gauge persistido | Última falha confirmada |
| `retention_unfinished_runs`, `recovery_unfinished_runs` | Gauge persistido | Inícios sem transição terminal; podem representar interrupções históricas, não workers necessariamente ativos |

Histogramas de tempo usam buckets até 30 s e +Inf; de tamanho, 512, 1024, 2048,
4096, 6144, 8192 bytes e +Inf. Falha de transporte sem conteúdo não produz amostra
de tamanho: não é artificialmente registrada como resposta de zero bytes. Rejeições
por limite de transporte permanecem observáveis por código, mesmo sem essa amostra.

A sonda informativa continua separada do scrape. `/metrics` lê apenas agregados
de PostgreSQL e memória; não conecta ao Ollama ou Graylog e não dispara trabalho.
Falhas do coletor não são substituídas por zeros de sucesso.

## Cardinalidade e compatibilidade

Os únicos labels de aplicação dessas famílias são `environment`, `result`,
`origin` e `code`, conforme necessário. `le` é o label automático dos histogramas;
job/instance podem ser acrescentados pelo Prometheus. Ambientes pertencem ao
catálogo development/test/homologation/production/unknown. Códigos vêm de conjuntos
fechados; não há organização, usuário, execução, assistência, modelo, hash ou texto
livre como dimensão.

A instrumentação inicial de contexto/gerador/persistência tinha labels
`sufficiency`, `section`, `state`, `rejection`, `operation` e `outcome`. Este contrato
uniformiza essas famílias existentes com os quatro labels permitidos. As expressões
anteriores que usarem tais labels devem ser migradas; o painel versionado anterior
não consumia essas famílias de IA. O contrato HTTP de resultado permanece 1.0.0.

Contadores em memória reiniciam com a instância. Contadores persistidos são derivados
do histórico imutável e sobrevivem ao processo do CLI/API; backup/restauração e a
política própria de retenção da auditoria continuam aplicáveis.
Os agregados persistidos são iguais em instâncias que consultam o mesmo banco:
usar max por ambiente, não sum. Calcular increase por série antes de deduplicar.
O agrupamento pressupõe um banco compartilhado por ambiente neste deploy;
implantações com bancos independentes precisam de contrato próprio.
Regras e painel filtram agregados pela coleta bem-sucedida. Flags/gauge de trabalho
em memória são por processo; chamadas ao provider podem ser somadas entre instâncias.

## Logs e incidentes

Cada fronteira emite evento estruturado com correlation ID da operação, duração,
estado, origem e código fechado. `state=none`/`origin=none` indicam campos sem
aplicação naquela fronteira, não um resultado inventado. Contexto, prompt, saída,
endpoint, nome/digest do modelo e identificadores de negócio não são acrescentados
aos logs. Hashes e identidades já aprovados continuam na auditoria, sem se tornarem
labels ou logs de conteúdo. Não foi adicionada uma infraestrutura nova de tracing.

Um 404 de resultado ausente não é incidente de acesso cruzado. O sinal
`scope_violation` exige uma conferência interna de organização e permissões no
caso negado, sem alterar a resposta pública. Falhas de integridade persistida
continuam registradas na auditoria; sua métrica durável também cobre leituras GET.
Rejeições comuns de conteúdo ficam separadas desses sinais.
O pin divergente permanece identificado pelo código `runtime_pin_mismatch` no
gerador; não precisa expor o nome do modelo como dimensão para ser detectado.

## Rotinas finitas e migration 0040

A migration `0040_add_ai_assistance_observability.sql` admite dois datasets fechados
na auditoria existente `data_operation_events`: `ai_assistance_results` e
`ai_assistance_reservations`, ambos sob a operação técnica `retention`. Não cria
uma nova trilha de auditoria ou altera dados de negócio.

Uma execução efetiva grava intenção curta antes do lote. Exclusões, eventos por
registro e sucesso do lote são confirmados na mesma transação; se a finalização
falhar, as exclusões e suas projeções são revertidas. A falha do lote é registrada
separadamente. Cada correlação admite no máximo um início e um resultado terminal;
repetir a mesma correlação não executa outro lote. Uma nova invocação do CLI usa
nova correlação e continua sujeita à seleção limitada/idempotente dos vencidos.

Os triggers existentes projetam as operações para `audit_event_catalog` e a fila
Graylog. São eventos técnicos globais: o coletor Graylog precisa de configuração
explícita autorizando eventos globais para entregá-los; a fila não prova recebimento.
Eventos por assistência mantêm seus escopos organizacionais anteriores.

Prévia não grava intenção/sucesso/falha de manutenção e não atualiza seu heartbeat.
Lote efetivo vazio é sucesso, com contagem zero. Se o processo morrer, o início sem
conclusão permanece consultável. Se o próprio banco estiver indisponível, não é
possível persistir sua falha nele: logs sanitizados, saída não zero do CLI,
`collection_success=0` e os controles de indisponibilidade do banco são necessários.

As métricas gerais de backup/retencão excluem esses dois datasets. Isso evita
promover falhas de manutenção de IA ao alerta crítico legado de recuperação de
dados; os sinais específicos alimentam os alertas warning da assistência.

Rollback 0040 remove os índices/guardas novos e **preserva eventos imutáveis** e
a aceitação dos dois valores de dataset, para manter o histórico consultável.
Não é uma restauração byte a byte do CHECK anterior. Reaplicar 0040 é suportado;
não apagar histórico para reverter a instrumentação. Não editar migrations já
publicadas. Desativação operacional continua sendo feita pelas flags.

Procedimentos: [runbook da assistência](runbooks/ai-assistance.md).

## Alertas e painel

Cinco regras em `observability/prometheus/alerts.yml`, vinculadas exatamente a
cinco runbooks específicos no contrato de homologação:

| Alerta (prefixo SynergiaAiAssistance) | Condição e recuperação | Severidade |
| --- | --- | --- |
| Unavailable | Razão unavailable/timeout sobre os seis resultados HTTP, rate de 5m, >20% por 10m; sai com razão ≤20%, sem tráfego na janela ou suspensão | warning |
| Stalled | Reservas >0, mais antiga ≥600s e última conclusão há ≥600s, com geração habilitada; sai com conclusão recente, esvaziamento ou suspensão | warning |
| IntegrityViolation | increase >0 em 5m de integridade/escopo confirmado ou pin divergente no gerador; sai sem incidentes novos na janela | critical |
| ExpiredReservationsGrowing | delta do gauge em 10m >0, estoque atual >0, por 2m; sai com estoque zero ou fim do crescimento na janela | warning |
| RetentionFailures | increase de failed ≥3 em 15m; sai quando as falhas deixam a janela, não apenas porque um lote teve sucesso | warning |

O relógio de Stalled já representa os dez minutos; não acrescenta outra espera
de dez minutos. Conclusão por falha é progresso e continua visível no alerta de
indisponibilidade. Não há alerta por uma rejeição comum isolada, por não existir
tráfego ou por flag desligada. Incidentes reais e manutenção continuam relevantes
mesmo com geração suspensa: essa flag só filtra disponibilidade e paralisação.
O counter de pin divergente nasce com zero para detectar o primeiro incremento
após uma coleta inicial; incidentes anteriores ao primeiro scrape não podem ser
reconstruídos por increase. A sonda não gera inferência nem esse counter.

Counters usam increase/rate por série (com tratamento de reset), gauges usam
delta. Valores de increase são extrapolados, inclusive a quantidade de falhas de
retenção: reconciliar números exatos com a auditoria. Não se promete detecção
de evento não coletado entre scrapes, nem de uma rotina que nunca foi agendada.
Collection 0/ausente significa medição indisponível; usar os alertas gerais de
coleta/API/banco e a indicação explícita no painel, não inferir zero falhas.

O dashboard **SYNERGIA Technical Overview** mantém os painéis existentes e
acrescenta 14: controles/coleta por instância, resultados HTTP, indisponibilidade,
p95 de durações/tamanhos, origens entregues, reservas/provider, relógio de progresso,
persistência, segurança, recuperação e estado das manutenções. Cada expressão
mantém ambiente e distingue counters em memória de agregados compartilhados.
Sem amostras não há quantil/taxa; **No data** não é substituído por zero.
Último sucesso/conclusão igual a zero é omitido da curva de idade, com significado
explicado no painel. O provisionamento existente continua local e somente leitura.

Validações sem credenciais e sem runtime de IA, a partir da raiz:

```bash
backend/.venv/bin/python scripts/validate_homologation_observability.py \
  --promtool-dashboard-dir /tmp/synergia-dashboard-checks
docker run --rm --entrypoint promtool \
  -v "$PWD/observability/prometheus:/etc/prometheus:ro" \
  prom/prometheus:v3.14.0 test rules \
  /etc/prometheus/alerts.test.yml /etc/prometheus/ai-assistance.test.yml
docker run --rm --entrypoint promtool \
  -v /tmp/synergia-dashboard-checks:/checks:ro \
  prom/prometheus:v3.14.0 check rules /checks/dashboard.rules.yml
docker run --rm --entrypoint promtool \
  -v /tmp/synergia-dashboard-checks:/checks:ro \
  prom/prometheus:v3.14.0 test rules /checks/dashboard.test.yml
```

Os testes novos de disparo, recuperação e ausência de alerta também executam no
CI junto da suíte anterior. O validador recusa URL de host/repositório incorreto,
runbook emprestado/ausente, severidade divergente e nomes duplicados; também
confere as vistas do painel. As consultas reais do dashboard são exportadas para
validação de sintaxe de todas as expressões e dez verificações semânticas por
séries sintéticas, sem cópias antigas das consultas. Os casos versionados referem
painel/target e o exportador usa apenas a biblioteca padrão Python. Promtool
valida a sintaxe YAML e PromQL, sem exigir Grafana ou modelo em execução.

Referências de semântica usadas: [funções PromQL](https://prometheus.io/docs/prometheus/latest/querying/functions/)
e [testes de regras com promtool](https://prometheus.io/docs/prometheus/latest/configuration/unit_testing_rules/).
