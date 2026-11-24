# Workorders: versão atual e histórico por organização

Contrato aditivo da API `0.18.0`, issue #195. A identidade organizacional é
`executions.organization_id` (UUID IAM). `organization_code` continua sendo
informação de negócio importada e nunca autoriza acesso.

## Busca paginada

`GET /search?type=workorder&query=WO-001&view=current`

- `view=history` é o default legado: retorna todos os snapshots elegíveis.
- `view=current` seleciona uma versão por `(organization_id, workorder_number)`.
- A seleção usa `updated_at DESC, snapshot_id DESC`, sem completar valores
  ausentes com dados de outra versão. `snapshot_id` é o ID persistido da Workorder.
- São elegíveis somente execuções `completed`/`completed_with_errors`, com IAM
  conhecido e dentro do escopo de `business.read`, inclusive para atores globais.
- `organization_id` restringe o recorte solicitado sem ampliar a autorização.
- `execution_id` fixa uma execução; `started_from`/`started_to` são limites
  inclusivos sobre **o início da execução**, com fuso horário obrigatório.
  O período é normalizado para UTC e aplicado antes da seleção da versão atual.
- Contagens e paginação são calculadas depois da seleção, no mesmo snapshot
  de leitura. A ordenação histórica legada permanece disponível.
- A resposta informa `view`; cada Workorder informa `organization_id`,
  `organization_name` IAM, `organization_code` de negócio, `execution_id`,
  `updated_at` e `snapshot_id`.
- Busca continua exata e preserva zeros à esquerda. Busca parcial pertence à #206.

Lotes e seriais continuam com suas consultas históricas existentes. Para esses
tipos, omitir `view` ou enviar `history`. Os parâmetros novos de seleção de
Workorder não são aplicados silenciosamente a outros tipos: a combinação
retorna `422 workorder_selection_not_supported`.

## Detalhe e consolidado

`GET /workorders/{numero}` e `GET /workorders/{numero}/consolidated-result`
continuam retornando **um** snapshot. Histórico paginado usa a busca acima.

- Aceitam `execution_id`, `organization_id`, `started_from` e `started_to`.
- Uma execução explícita mantém a versão selecionada, mesmo que exista outra
  mais recente; todos os filtros e permissões continuam sendo aplicados.
- Sem execução explícita, selecionam a versão atual na organização/recorte.
- Se o número existir em várias organizações autorizadas sem desambiguação,
  retornam `409 ambiguous_workorder`. O erro não enumera organizações ou versões.
- Combinação inexistente, sem IAM, não publicada ou fora do escopo retorna 404.
- Lotes, seriais, pendências, quantidades e proveniência pertencem à execução
  selecionada. O consolidado não escolhe novamente uma versão para cada seção.

A identidade adicional também aparece na lista de Workorders relacionada aos
indicadores; seus links e os links de Workorder nos relatórios preservam
`execution_id` e `organization_id` ao abrir o detalhe. Os totais e a seleção
do painel continuam sob a #196; cobertura de fontes pertence à #197. Nenhum
snapshot emitido de relatório é modificado por esta entrega.

## Interface e navegação

- A consulta de Workorders envia `view=current` explicitamente por padrão.
  O seletor **Versões** permite consultar **Histórico**. Cada linha atual também
  oferece **Ver histórico**, limitado à organização IAM daquela linha e ao
  recorte já aplicado.
- Organização IAM, execução e início das execuções podem ser filtrados no
  painel recolhível. Datas digitadas usam o fuso do perfil; a URL registra
  instantes UTC. Paginar ou reaplicar filtros sem editar as datas preserva
  inclusive a precisão de microssegundos recebida na URL.
- URL, recarga e retorno do detalhe mantêm modo, organização, execução,
  período, ordenação e página. O detalhe abre com a organização e a execução
  da linha, sem substituir uma versão histórica pela atual.
- A organização IAM é apresentada separadamente do código importado. As datas
  de atualização pertencem a cada snapshot; o horário de referência da resposta
  continua sendo o instante de geração da consulta.
- Mudanças de seleção cancelam a requisição anterior e limpam o detalhe antes
  de carregar a nova versão. Ambiguidade não provoca escolha automática de
  organização; a interface orienta o retorno à consulta.
- Lotes e seriais não recebem os filtros de seleção de Workorder.

`web/e2e/workorder-versions.spec.ts` verifica a jornada no navegador, paginação,
retorno e recarga com contratos HTTP sintéticos, nos dois temas e em
390/768/1440 px. O cenário opt-in `E2E_NATIVE_ZOOM=true` verifica zoom nativo de
250%. Esses testes de interface complementam os testes PostgreSQL e de
autorização real; não substituem a validação integrada da entrega.

Roteiro, matriz de aceite, limitações e evidências da campanha estão em
[Validação da #195](workorder-snapshots-validation.md).
