# Contratos da API

Os contratos administrativos de usuarios, incluindo autorizacao temporaria por
contexto confiavel, filtros, concorrencia otimista e ciclo de vida, estao em
[user-administration.md](user-administration.md). O OpenAPI publica essas rotas
sob a tag `user administration`.

Consulte também [Acompanhamento de execuções](execution-monitoring.md) para os
contratos integrados de estado, divergências, classificações, pendências e evidências.

A API FastAPI é a fronteira pública do backend. Clientes não devem consultar o
PostgreSQL nem ler arquivos importados diretamente. A especificação executável
fica em `/openapi.json` e a interface interativa em `/docs`.

A API emite sessões, access tokens JWT e refresh tokens rotativos conforme
[autenticação e sessões](authentication.md). Login local permanece restrito a
ambientes não produtivos; a integração corporativa continua bloqueada pelos
portões da [ADR 0001](adr/0001-identity-strategy.md). A aplicação de RBAC e
escopo organizacional a todas as operações existentes será incremental.

## Recursos e códigos HTTP

| Método e rota | Resultado | Sucesso |
| --- | --- | --- |
| `GET /health/live` | confirma que o processo responde, sem consultar dependências | `200` |
| `GET /health/ready` | confirma PostgreSQL, schema e armazenamento; falha fechada | `200`/`503` |
| `GET /health` | apresenta estado sanitizado de dependências críticas e opcionais | `200`/`503` |
| `GET /metrics` | métricas Prometheus com credencial técnica dedicada | `200` |
| `POST /auth/login` | cria sessão e emite access/refresh pelo adaptador configurado; hoje só o local (desenvolvimento, teste e homologação temporária); `503 identity_adapter_unavailable` quando desabilitado e `503 auth_configuration_invalid` com configuração inválida; contrato corporativo em [corporate-identity-contract.md](corporate-identity-contract.md) | `200` |
| `GET /me` | consulta identidade e preferências próprias | `200` |
| `PATCH /me` | atualiza perfil, notificações e aparência próprias com versão otimista | `200` |
| `POST /me/avatar` | valida e grava avatar próprio | `201` |
| `GET /me/avatar` | baixa avatar próprio após autenticação | `200` |
| `DELETE /me/avatar` | remove avatar próprio | `200` |
| `POST /auth/refresh` | rotaciona refresh e renova access | `200` |
| `POST /auth/logout` | revoga a sessão atual | `200` |
| `POST /auth/logout-all` | revoga as sessões próprias | `200` |
| `GET /auth/sessions` | lista somente sessões próprias ativas com metadados sanitizados | `200` |
| `DELETE /auth/sessions/{session_id}` | revoga sessão própria específica; `404` uniforme para ausente, alheia ou inativa | `200` |
| `POST /auth/sessions/revoke-others` | revoga outras sessões próprias, mantendo a atual | `200` |
| `POST /imports` | inicia uma importação rastreável | `201` |
| `GET /imports/policy` | políticas por fonte e organizações ativas autorizadas | `200` |
| `GET /imports/{execution_id}/inspections` | decisões de segurança dos arquivos | `200` |
| `GET /executions` | catálogo paginado e filtrado no escopo autorizado, com `generated_at` UTC referente ao cálculo da resposta | `200` |
| `GET /executions/{execution_id}` | estado e tentativa da execução | `200` |
| `GET /imports/{execution_id}/validation-report` | erros e avisos | `200` |
| `GET /workorders/{workorder_number}` | Workorder, lotes e seriais | `200` |
| `GET /search` | busca exata e paginada por Workorder, lote ou serial | `200` |
| `GET /lots/{lot_number}` | lote e seus seriais | `200` |
| `GET /serials/{serial_number}` | serial, lote e Workorder | `200` |
| `GET /pending-items` | fila de pendências | `200` |
| `GET /pending-items/{pending_id}` | detalhe da pendência | `200` |
| `GET /history` | eventos auditáveis | `200` |
| `GET /workorders/{workorder_number}/consolidated-result` | consolidado | `200` |
| `POST /executions/{execution_id}/reprocess` | cria nova tentativa | `202` |
| `GET /indicators` | totais operacionais básicos; aceita `organization_id`, `date_from` e `date_to` | `200` |
| `GET /indicators/{entity}` | registros paginados do indicador; exige `dashboard.read` e permissão específica da entidade | `200` |
| `GET /indicators/{entity}` | registros paginados relacionados aos indicadores com o mesmo escopo e período | `200` |
| `GET /admin/access/permissions` | catálogo versionado de permissões | `200` |
| `GET /admin/access/organizations` | organizações ativas para escopo administrativo | `200` |
| `GET /admin/access/associations` | associações paginadas e filtráveis por entidade, organização e estado | `200` |
| `GET /admin/access/users/{user_id}/effective-permissions` | permissões efetivas e origens | `200` |
| `POST /reports` | gera e persiste o primeiro snapshot de um relatório | `201` |
| `POST /reports/{report_id}/versions` | gera uma nova versão sem sobrescrever anteriores | `201` |
| `GET /reports` | catálogo paginado, mostrando a versão mais recente | `200` |
| `GET /reports/policy` | tipos, filtros, formatos e organizações disponíveis na jornada web | `200` |
| `GET /reports/{report_id}` | dados da versão mais recente | `200` |
| `GET /reports/{report_id}/versions` | histórico paginado | `200` |
| `GET /reports/{report_id}/versions/{version}` | metadados e snapshot de uma versão | `200` |
| `GET /reports/{report_id}/versions/{version}/export` | exporta o snapshot persistido em CSV ou JSON | `200` |
| `POST /reports/{report_id}/versions/{version}/cancel` | cancela uma geração ainda em andamento | `200` |
| `GET /notifications` | lista paginada de notificações internas próprias | `200` |
| `GET /notifications/unread-count` | conta notificações próprias não lidas | `200` |
| `PATCH /notifications/{notification_id}/read` | persiste a leitura individual com versão otimista | `200` |
| `POST /notifications/read-all` | persiste a leitura em lote dentro do escopo atual | `200` |
| `GET /admin/notification-templates/policy` | eventos permitidos, placeholders, canais, locales e estado do e-mail | `200` |
| `GET /admin/notification-templates` | catálogo paginado e histórico filtrável de revisões | `200` |
| `POST /admin/notification-templates/drafts` | cria nova revisão editável e auditada | `201` |
| `GET /admin/notification-templates/{revision_id}` | consulta uma revisão exata | `200` |
| `PATCH /admin/notification-templates/{revision_id}` | altera somente rascunho com versão otimista | `200` |
| `POST /admin/notification-templates/{revision_id}/preview` | renderiza prévia exclusivamente sintética | `200` |
| `POST /admin/notification-templates/{revision_id}/publish` | publica e ativa uma revisão imutável | `200` |
| `POST /admin/notification-templates/{revision_id}/deactivate` | encerra a ativação sem excluir histórico | `200` |

Recursos inexistentes retornam `404`, estado incompatível retorna `409`, corpo
ou parâmetros inválidos retornam `422`, arquivo acima do limite retorna `413`,
tipo/extensão incompatível retorna `415`, e falhas inesperadas retornam `500`
sem expor detalhes internos.

## Erros padronizados

Toda resposta de erro possui o mesmo envelope:

```json
{
  "error": {
    "code": "execution_not_found",
    "message": "Execution não encontrado",
    "details": {"identifier": "exec-inexistente"}
  }
}
```

`code` é estável para tratamento pelo frontend; `message` é legível; `details`
traz somente contexto seguro. Erros de validação usam
`request_validation_error` e incluem uma lista `issues`.

## Importação com múltiplas fontes

`POST /imports` aceita um ou mais pares `source`/`file` em `multipart/form-data`.
Os campos são posicionais: a primeira fonte descreve o primeiro arquivo, e assim
por diante. Quantidades diferentes retornam `422` com
`source_file_mismatch`. Um único par mantém o comportamento anterior.

Todos os arquivos do pedido pertencem ao mesmo `execution_id`. Cada arquivo é
reservado no banco antes do pipeline e recebe um `source_file_id` real, usado
nos registros importados, normalizados e na proveniência consolidada. A
normalização de todas as fontes elegíveis é reunida antes da consolidação, o que
torna alcançáveis a precedência e as divergências multifuente pelo fluxo HTTP.

Antes da reserva e do pipeline, cada arquivo permanece em quarentena e passa
pela política da fonte. Uma rejeição retorna `reason_code` estável e deixa
metadados consultáveis em `GET /imports/{execution_id}/inspections`; a resposta
nunca inclui caminho absoluto, chave de storage ou nome interno. Formatos,
limites, inspeções de conteúdo e retenção estão em
[upload-security.md](upload-security.md).

A fonte `WO Status` (somente XLSX) reúne abas de várias fontes lógicas: cada aba
autorizada entra no pipeline com a fonte N-FP, OWM ou TMS, e `GET /imports/policy`
lista a política da fonte composta. Os adapters, as abas e os códigos de rejeição por
linha estão em [wo-status-adapters.md](wo-status-adapters.md).

Uma rejeição por capacidade de uma planilha (`workbook_*`, `ingestion_*`,
`no_authorized_sheet` e `unreadable_workbook`) usa o envelope de erro comum e
acrescenta a `error.details` os campos `guidance` e, quando aplicável, `limit`,
`observed` e `sheet`. Os limites `workbook_*` respondem `413`; os demais,
`422`. A execução termina como `failed` com o código como motivo, sem registros
parciais, e o mesmo arquivo pode ser reenviado depois de ajustado o orçamento.
Os códigos e a operação estão em
[xlsx-ingestion-budget.md](xlsx-ingestion-budget.md).

## Paginação, filtros e ordenação

`GET /executions`, `GET /pending-items` e `GET /history` aceitam `page` (padrão `1`) e
`page_size` (padrão `25`, máximo `100`). A resposta informa:

```json
{
  "items": [],
  "pagination": {"page": 1, "page_size": 25, "total": 0, "pages": 0},
  "sort": "oldest",
  "generated_at": "2026-09-04T12:00:00Z"
}
```

Em `GET /executions`, o `page_size` padrão é `20`. O campo `generated_at` é o
instante UTC, com fuso horário, em que o servidor calculou o catálogo. Ele pode
ser usado pela interface para informar a atualidade da consulta, sem representar
o início ou o término de qualquer execução.

A fila retorna apenas pendências `open` por padrão. Ela pode ser filtrada por
`status`, `category`, `priority`, `responsible_area`, `workorder_number`,
`lot_number`, `serial_number` e `execution_id`, e ordenada por `oldest`,
`newest`, `priority` ou `category`. O detalhe inclui o código e a versão da
regra, a área responsável e a evidência persistida como objeto JSON. O histórico pode ser filtrado por
`execution_id`, `entity_type`, `entity_id` e `event_type`, com ordem `newest`
ou `oldest`. Critérios de desempate por ID deixam os resultados determinísticos.

Consultas de Workorder aceitam `execution_id`; consultas de lote aceitam
`workorder_number`. Sem esses filtros, a versão mais recentemente atualizada é
retornada quando o identificador aparece em mais de uma execução.

## Reprocessamento

```http
POST /executions/exec-001/reprocess
Content-Type: application/json

{"technical_origin":"web"}
```

A operação cria uma nova execução `reprocessing`, incrementa `attempt`,
referencia a execução raiz em `reprocessed_from_execution_id` e registra o
evento `reprocessing_requested`. `idempotency_key`, `pipeline_version` e
`rule_catalog_version` fazem parte da reserva transacional; uma repetição
idêntica retorna a mesma execução com `idempotent_replay=true`. A execução
anterior e seus resultados permanecem inalterados e consultáveis. Estados
ativos ou não reprocessáveis são rejeitados com `409` e código
`execution_still_active`.

## Massa sintética

Os testes de contrato usam a Workorder `WO-SYN-001`, lote `LOT-SYN-001` e serial
`SER-SYN-001`. O teste de persistência exercita os contratos no PostgreSQL,
inclusive a preservação da execução anterior. O arquivo
`data/synthetic/database_example.json` fornece uma massa mínima adicional.

## Decisões de contrato

- Seriais, lotes e Workorders permanecem texto para preservar zeros à esquerda.
- A prioridade da pendência é persistida com a versão do catálogo que produziu
  o resultado; dados legados sem prioridade usam o catálogo atual como fallback.
- O consolidado restringe holds, decisões OQC, pendências, classificações,
  avaliações de regras e proveniência à execução escolhida.
- Indicadores agregados não substituem o histórico auditável.
- Notificações, integrações RPA e a aplicação geral de autorização permanecem
  fora desta etapa; autenticação e sessões seguem o ADR e a matriz de acesso.

## Total Decision — API 0.8.0

`POST /imports` aceita `source=Total Decision` com XLSX e organização IAM autorizada. `GET /imports/policy` anuncia apenas `xlsx` para essa fonte, mesmo quando a configuração global permite CSV/JSON. O arquivo e a execução guardam `Total Decision`; os registros entregues ao pipeline são GMES/OQC. A migration `0032` amplia apenas as três restrições de fonte.

O adapter valida os dois níveis de cabeçalho, exclui a linha de totais e preserva proveniência. Conteúdo de usuário e observação vira apenas presença antes de qualquer registro importado, transformação ou artefato normalizado. `ORG_ID` da origem não autoriza acesso nem se torna organização IAM. Campos ambíguos não criam decisões humanas ou equivalências entre IDs.

Exemplo (token e organização obtidos pelo fluxo autenticado existente):

```bash
curl -X POST http://localhost:8000/imports \
  -H 'Authorization: Bearer <access-token>' \
  -F 'source=Total Decision' \
  -F 'organization_id=<organizacao-autorizada>' \
  -F 'file=@data/synthetic/total-decision_minimal.xlsx'
```

A seleção da fonte pela interface Angular fica para issue própria; este incremento é de backend. Consulte [o contrato do adapter](total-decision-adapter.md).


## Entrega externa de e-mail — API 0.9.0

`GET /admin/notification-templates/policy` acrescenta `smtp` aos valores de
`external_delivery`: `disabled`, `local_capture`, `smtp`, `unavailable`. A resposta
é apenas de configuração, sem conexão SMTP, envio, endereço ou segredo. Uma
configuração inválida retorna `unavailable`; o canal desabilitado ignora parâmetros
SMTP. `external_delivery_corporate` permanece `false` e não é inferido pelo host.

O incremento de `0.8.0` para `0.9.0` acompanha modelos OpenAPI, Angular e testes.
Implante backend e frontend da mesma revisão. A prévia de templates continua
sintética e sem envio. A execução opt-in fica nos comandos operacionais, sem
novo endpoint HTTP de transmissão. Configuração e aceite pendente do smoke real
estão em [smtp-email-provider.md](smtp-email-provider.md).
