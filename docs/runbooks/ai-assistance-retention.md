# Assistência — falhas repetidas da retenção

Alerta `SynergiaAiAssistanceRetentionFailures` (warning): aumento estimado de
pelo menos 3 transições failed de lotes efetivos na janela móvel de 15 minutos.
Prévia não produz heartbeat nem falha de manutenção; lote efetivo vazio é
sucesso. Os counters vêm da auditoria PostgreSQL, sobrevivem ao CLI e são
deduplicados entre instâncias da API. increase usa extrapolação do Prometheus:
confirmar a quantidade exata na auditoria, nunca usar a estimativa para faturamento.

## Diagnosticar

1. Conferir **AI maintenance failures**, **AI maintenance success age** e
   **AI unfinished maintenance**, junto de `collection_success=1`.
2. Consultar logs do CLI pelo correlation ID e eventos globais de
   `data_operation_events`/`audit_event_catalog`, dataset `ai_assistance_results`.
   Examinar started/succeeded/failed e os códigos, sem exportar DSN ou conteúdo.
   Início sem terminal pode ser uma interrupção histórica, não um job em execução.
3. Verificar migration 0040, acesso ao banco e existência da identidade técnica.
   Se o banco inteiro caiu, não é possível gravar sua própria falha: conferir
   saída não zero do processo, logs e alertas gerais de banco/coleta. Zero ou
   ausência de coleta não significa zero falhas. O alerta não supervisiona a
   ausência de agendamento; acompanhar também idade do último sucesso.

## Executar a rotina

Na raiz, com DATABASE_URL e configuração privados já fornecidos e identidade
autorizada existente, confirmar a prévia limitada:

```bash
read -r -p 'UUID da identidade técnica existente: ' AI_ASSISTANCE_ACTOR_ID
export AI_ASSISTANCE_ACTOR_ID
PYTHONPATH=backend backend/.venv/bin/python scripts/expire_ai_assistance.py \
  --actor-id "$AI_ASSISTANCE_ACTOR_ID" --batch-size 100 --dry-run
```

Após conferir quantidade/intervalo e corrigir a causa, executar o lote efetivo:

```bash
PYTHONPATH=backend backend/.venv/bin/python scripts/expire_ai_assistance.py \
  --actor-id "$AI_ASSISTANCE_ACTOR_ID" --batch-size 100
```

Neste CLI, **omitir `--dry-run` executa exclusão** dos resultados elegíveis segundo
a retenção configurada (e reservas expiradas); ele não usa `--apply`. O histórico
imutável permanece. Não alterar a política de retenção para forçar o teste.
Conferir succeeded e record_count, logs e outbox da mesma correlação. Eventos
técnicos globais precisam de exportação global explicitamente autorizada para
chegar ao Graylog; presença na outbox não prova recebimento.

## Recuperação

Confirmar um lote efetivo bem-sucedido, mesmo vazio, auditoria e coleta saudáveis.
Três falhas recentes continuam na janela mesmo após um sucesso: o alerta recupera
quando o aumento de falhas fica abaixo do limiar, sem apagar histórico. Não
repetir lotes indiscriminadamente para tentar apagar o sinal.
A retenção continua necessária com geração suspensa. Se ela foi suspensa pelo
incidente, só reabilitar após os critérios do [runbook comum](ai-assistance.md).
