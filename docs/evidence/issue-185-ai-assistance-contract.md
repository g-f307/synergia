# Validação da fundação de assistência — issue #185

Data: 2026-11-14. Base: `424beb09601e3d36338165135ea9afbb49503afd`.
Contrato 1.0.0, API 0.12.0, catálogo RBAC 1.6.0.

## Resultados locais

| Comando / escopo | Resultado |
| --- | --- |
| Backend: `pytest -q -m 'not integration' --tb=short` | 2053 aprovados; 807 desmarcados; 16 subtests aprovados |
| `pytest -q tests/test_ai_assistance_contract.py tests/test_ai_assistance_config.py tests/test_ai_assistance_access.py tests/test_ai_assistance_errors.py --tb=short` | 133 aprovados |
| PostgreSQL 16: `test_ai_assistance_persistence.py`, `test_authorization_persistence.py`, `test_access_control_persistence.py` | 18 aprovados |
| PostgreSQL 16: `test_security_matrix_persistence.py` | 550 aprovados |
| Backend: `ruff check . ../scripts` | aprovado |
| Web: `npm run lint` e `npm run build` | aprovados |
| Web: `npm test -- --watch=false --browsers=ChromeHeadless` | 351 aprovados, incluindo 3 de capacidade |
| `validate_access_matrix.py`, `validate_web_journey_map.py`, `validate_threat_model.py`, `validate_stage5_release.py`, `validate_stage6_pilot.py`, `validate_http_security.py`, `security_matrix.py --check` | aprovados |
| `python -m compileall -q backend/app scripts/apply_migrations.py` | aprovado |
| `git diff --check` | aprovado |

Python 3.12 no backend; Node 22.18.0 e ChromeHeadless no frontend. Avisos de
depreciação do Starlette e de orçamento CSS em componentes existentes não
impediram as validações. Os testes de PostgreSQL aplicaram migrations 0001–0037
em banco descartável, encerrado após uso; os dados do ambiente foram preservados.

## Cobertura observável

- Entrada `{}` aceita e prompt/texto livre recusado com 422 em contrato HTTP.
- Quatro estados e exemplos, tipos estritos, campos extras, limites de texto/listas,
  hashes, digest, tempos e fuso; snapshot OpenAPI versionado.
- Referências únicas e opacas exigem presença no conjunto autorizado; ausência de
  contexto, URLs ou referências inventadas são recusadas.
- Limites de 8192 bytes contabilizam UTF-8; resposta inválida em UTF-8 é recusada.
- Falhas padronizadas 409/422/503/504; ausência de sessão/permissão e invisibilidade
  verificadas com 401/403/404, incluindo escopos disjuntos e globais.
- Grants reais apenas a gestor/analista; leitura e geração independentes;
  rollback desativa permissões e preserva histórico.
- Flag desligada e liveness; capacidade pública limitada a três booleanos.
- Endpoint externo, credenciais/query/fragmento/path, placeholders, ausência de
  digest e limites inseguros impedem inicialização nos perfis previstos.

## Limites desta evidência

Os resultados são locais, não representam CI remota nem execução assistida do
piloto. Os gates das Etapas 5/6 preservam sua decisão sem autorização de liberação.
Não houve inferência, download de modelo, ativação da flag, persistência de
resultados ou alteração visual. Runtime, fundamentação, concorrência efetiva,
expiração e interface são responsabilidades #186–#192 descritas no
[ADR 0002](../architecture/0002-ai-assistance.md). O filtro lexical não é prova
de segurança semântica; fundamentação e revisão de evasões continuam obrigatórias.

## Correções após revisão do PR #216

A CI inicial encontrou quatro falhas de rollback por manter o catálogo 1.6.0
ativo ao reativar versões antigas. Os testes de auditoria, feedback, templates,
SMTP e Graylog agora revertem `0037` antes das migrations anteriores, em LIFO.
As migrations e os scripts de rollback publicados não foram modificados.

O probe de baseline agora exige catálogo 1.6.0 ativo, ambas as permissões
reservadas e ativas para `execution` e exatamente os quatro grants ativos de
Gestor/Analista, com papéis ativos. Doze novos casos recusam catálogo/permissão
inativos, grants ausentes/indevidos/revogados e papel inativo. A recusa não
registra nenhuma migration; a adoção de uma base completa continua aprovada.

| Validação da correção | Resultado local |
| --- | --- |
| `pytest -q backend/tests/test_migration_runner.py backend/tests/test_audit_persistence.py backend/tests/test_feedback_persistence.py backend/tests/test_notification_templates_persistence.py backend/tests/test_smtp_queue_persistence.py backend/tests/test_graylog_persistence.py --tb=short` | 140 aprovados |
| Backend: `pytest -q -m 'not integration' --tb=short` | 2053 aprovados; 819 desmarcados; 16 subtests aprovados |
| Backend: `ruff check . ../scripts` | aprovado |
| `git diff --check` | aprovado |

Resultados da execução completa de persistência e da CI remota são registrados
na descrição do PR, distinguindo-os destes resultados direcionados locais.
