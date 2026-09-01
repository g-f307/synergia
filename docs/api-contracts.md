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

A API atual ainda não aplica autenticação. A política-alvo classifica todas as
operações de negócio como privadas e está inventariada na
[matriz inicial de acesso](access-control-matrix.md); `/health` é a única
operação pública. A estratégia de identidade e sessão está no
[ADR 0001](adr/0001-identity-strategy.md). Esses documentos não ativam uma
integração nem substituem a implementação posterior dos controles.

## Recursos e códigos HTTP

| Método e rota | Resultado | Sucesso |
| --- | --- | --- |
| `POST /imports` | inicia uma importação rastreável | `201` |
| `GET /imports/{execution_id}/inspections` | decisões de segurança dos arquivos | `200` |
| `GET /executions/{execution_id}` | estado e tentativa da execução | `200` |
| `GET /imports/{execution_id}/validation-report` | erros e avisos | `200` |
| `GET /workorders/{workorder_number}` | Workorder, lotes e seriais | `200` |
| `GET /lots/{lot_number}` | lote e seus seriais | `200` |
| `GET /serials/{serial_number}` | serial, lote e Workorder | `200` |
| `GET /pending-items` | fila de pendências | `200` |
| `GET /pending-items/{pending_id}` | detalhe da pendência | `200` |
| `GET /history` | eventos auditáveis | `200` |
| `GET /workorders/{workorder_number}/consolidated-result` | consolidado | `200` |
| `POST /executions/{execution_id}/reprocess` | cria nova tentativa | `202` |
| `GET /indicators` | totais operacionais básicos | `200` |
| `GET /admin/access/permissions` | catálogo versionado de permissões | `200` |
| `GET /admin/access/associations` | associações administrativas paginadas | `200` |
| `GET /admin/access/users/{user_id}/effective-permissions` | permissões efetivas e origens | `200` |

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

## Paginação, filtros e ordenação

`GET /pending-items` e `GET /history` aceitam `page` (padrão `1`) e
`page_size` (padrão `25`, máximo `100`). A resposta informa:

```json
{
  "items": [],
  "pagination": {"page": 1, "page_size": 25, "total": 0, "pages": 0},
  "sort": "oldest"
}
```

A fila retorna apenas pendências `open` por padrão. Ela pode ser filtrada por
`status`, `category`, `workorder_number` e `execution_id`, e ordenada por
`oldest`, `newest` ou `category`. O histórico pode ser filtrado por
`execution_id`, `entity_type`, `entity_id` e `event_type`, com ordem `newest`
ou `oldest`. Critérios de desempate por ID deixam os resultados determinísticos.

Consultas de Workorder aceitam `execution_id`; consultas de lote aceitam
`workorder_number`. Sem esses filtros, a versão mais recentemente atualizada é
retornada quando o identificador aparece em mais de uma execução.

## Reprocessamento

```http
POST /executions/exec-001/reprocess
Content-Type: application/json

{"technical_origin":"frontend-angular"}
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
- A implementação de autenticação, notificações e integrações RPA permanece
  fora desta etapa; as decisões preparatórias de identidade e autorização estão
  versionadas no ADR e na matriz de acesso.
