# Relatórios persistentes

Relatórios são snapshots dos dados já importados e persistidos. A geração não
abre planilhas nem arquivos de origem. Cada versão registra a execução, o UUID
IAM da organização, o usuário e a sessão solicitantes, os filtros, o horário de
referência e a versão do schema do resultado.

## Tipos e conteúdo

- `workorder_consolidated`: Workorders com estado, organização observada,
  lotes, contagens e quantidades consolidadas;
- `oqc_summary`: lotes e Workorders com decisão OQC, motivos, pendência,
  prioridade e organização observada, além de totais por motivo, prioridade e
  organização e contagem de lotes distintos.

Quantidades ausentes permanecem JSON `null`; zero somente representa zero
persistido. Uma classificação automática pode aparecer como contexto, mas não
é convertida em aprovação humana.

## Estados e completude

`generating` é o estado inicial. A única transição aceita é para `succeeded`,
`failed` ou `cancelled`. Estados terminais não podem ser reabertos. Falhas
preservam código seguro, mensagem limitada e eventos auditáveis. Uma geração
persistida que ainda esteja em `generating` pode ser cancelada por usuário com
`report.cancel` em `POST /reports/{report_id}/versions/{version}/cancel`; motivo,
ator e correlação ficam registrados. Versões terminais retornam `409`.

`complete` corresponde a uma execução `completed`; `partial` corresponde a
`completed_with_errors`. Execuções ainda ativas, canceladas ou falhas retornam
`409`. Execuções inexistentes ou de outra organização são indistinguíveis e
retornam `404`.

## Versionamento e imutabilidade

`POST /reports` cria a identidade e a versão 1. Uma nova geração do mesmo
relatório usa `POST /reports/{report_id}/versions` e recebe o próximo inteiro.
Execução, filtros, referência e snapshot de uma versão não são atualizáveis.
Triggers rejeitam sobrescrita e remoção de versões e artefatos; mudanças
legítimas sempre criam outra versão.

O catálogo `GET /reports` é paginado, aceita filtros `organization_id`,
`report_type`, `state` e `execution_id`, e retorna a versão mais recente de cada
relatório. O histórico e os dados exatos são consultados em
`GET /reports/{report_id}/versions` e
`GET /reports/{report_id}/versions/{version}`. Consultas de dados geram
`report.consulted`.

Filtros aceitos: `date_from`, `date_to`, `state`, `workorder_number`,
`lot_number` e `priority`. Campos sem aplicação ao tipo são inócuos. A data é
aplicada ao `updated_at` persistido da entidade principal. `reference_at` é o
limite superior efetivo de todo o snapshot: a entidade principal e cada lote,
serial ou pendência relacionada só entram quando seu próprio `updated_at` é
menor ou igual ao corte. Não se reconstrói uma versão anterior de uma linha que
foi atualizada depois do corte; essa linha é excluída integralmente. Filtros
incompatíveis com o tipo retornam `422`.

Veja um payload sintético em
[`data/synthetic/report_examples.json`](../data/synthetic/report_examples.json).
