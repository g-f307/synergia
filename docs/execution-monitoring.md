# Acompanhamento de execuções

Esta API expõe o estado persistido do pipeline sem depender dos arquivos importados.
Todos os contratos usam o PostgreSQL como fonte de verdade e erros seguem o envelope
`{"error":{"code":"...","message":"...","details":{}}}`.

## Contratos

- `GET /executions`: catálogo paginado no escopo autorizado, com filtros por
  organização, estado persistido e público, origem, tipo de arquivo, período e
  identificador. A ordem usa `started_at` e `id` como desempate determinístico.
  A resposta inclui `generated_at`, instante UTC com fuso horário que registra
  quando o servidor calculou o catálogo; o campo informa a referência temporal
  da consulta e não substitui `started_at` ou `finished_at` dos itens.
- `GET /executions/{id}`: estado atual, ciclo (`active`, `completed`, `partial` ou
  `failed`), versões, datas, relação de reprocessamento, histórico e contagens.
- `GET /executions/{id}/divergences`: erros e avisos paginados. Aceita `source`,
  `severity`, `code`, `workorder`, `date_from`, `date_to`, `page`, `page_size` e
  `sort=oldest|newest`.
- `GET /executions/{id}/classifications`: classificações paginadas e respectivas
  regras, prioridades, justificativas e evidências estruturadas.
- `GET /executions/{id}/pending-items`: pendências paginadas da execução.
- `GET /executions/{id}/evidences`: catálogo paginado dos arquivos aprovados.
- `GET /executions/{id}/evidences/{evidence_id}/download`: download controlado.

A ordenação de todas as listas é estável por data ou identificador e sempre possui
desempate pelo identificador público. As evidências são
identificadas por número e nome gerado; nomes originais, `storage_key`, caminhos de
quarentena e caminhos absolutos nunca fazem parte das respostas. Arquivos rejeitados
retornam `403 evidence_not_allowed`.

As contagens de arquivos distinguem `files_received`, `files_accepted` e
`files_rejected`. O campo legado `files` representa todos os recebimentos inspecionados,
inclusive os rejeitados. Em evidências, `available` somente é verdadeiro quando existe
uma chave de armazenamento segura e o arquivo está fisicamente disponível.

## Cenários de estado

| Ciclo público | Estados persistidos |
|---|---|
| `active` | `pending`, `validating`, `normalizing`, `consolidating`, `applying_rules`, `reprocessing` |
| `completed` | `completed`, `duplicate` |
| `partial` | `completed_with_errors` |
| `failed` | `validation_failed`, `failed`, `cancelled` |

O Swagger em `/docs` e o OpenAPI em `/openapi.json` são a referência executável dos
parâmetros e modelos.

## Situação canônica e agregado autorizado (#193)

A API `0.15.0` acrescenta `outcome` ao catálogo e ao detalhe. O `status`
persistido permanece disponível. O `lifecycle` da tabela acima é legado e está
depreciado para métricas/apresentação: seu enum e comportamento continuam iguais,
incluindo duplicatas como `completed` e canceladas como `failed`. Consumidores
atualizados devem usar a situação canônica:

| `outcome` | Estados persistidos |
| --- | --- |
| `active` | `pending`, `validating`, `normalizing`, `consolidating`, `applying_rules`, `reprocessing` |
| `completed` | `completed` |
| `partial` | `completed_with_errors` |
| `skipped_duplicate` | `duplicate` |
| `failed` | `validation_failed`, `failed` |
| `cancelled` | `cancelled` |
| `unknown` | valor legado não reconhecido; nunca apresentado como sucesso |

`GET /executions/summary` exige `execution.read` e aceita os mesmos filtros do
catálogo: `organization_id`, `source`, `file_type`, `date_from`, `date_to`,
`status`, `outcome`, `execution_id` e `lifecycle` legado. Paginação e ordenação
não participam do agregado. A rota estática precede `/executions/{execution_id}`.

A resposta contém `generated_at`, `scope.permission`, `scope.organization_ids`,
`filters`, `total`, `by_outcome` e `by_source`. Todas as sete categorias de
`by_outcome` estão presentes, inclusive quando zeradas. Cada fonte contém total,
as mesmas categorias, volume `rows_read` e `latest_started_at`; `source: null`
preserva execuções sem fonte informada. Os totais somam o conjunto autorizado
completo, antes da paginação. Os exemplos OpenAPI incluem as sete categorias.

O predicado é comum a catálogo e agregado. Organização solicitada apenas
restringe o escopo; filtro incompatível retorna conjunto vazio, sem nomes ou
totais externos. Registros sem organização IAM são excluídos inclusive para
permissões globais. Respostas incluem o escopo da permissão e filtros efetivos;
comparar telas exige ambos iguais. O filtro de organização aparece em `filters`
e não redefine `scope.organization_ids`, que continua declarando o escopo da
permissão consultada, inclusive para atores globais ou com múltiplas organizações. `401` representa autenticação ausente/inválida,
`403` falta de permissão e `422` filtros inválidos. Detalhes inacessíveis mantêm
`404`, conforme a política existente.

`date_from`/`date_to` de catálogo/resumo exigem instantes ISO-8601 com fuso,
normalizados em UTC, e ambos os limites são inclusivos. Ausência de fuso retorna
`422 timezone_required`; intervalo invertido, `422 invalid_period`.

### Compatibilidade dos indicadores

`GET /indicators` continua exigindo apenas `dashboard.read`. Seu novo
`execution_summary` usa o mesmo serviço, com o escopo dessa permissão, nunca o
escopo de `execution.read`. O mapa legado `executions` continua agrupado por
status técnico, e `filters` mantém os campos legados. Os filtros canônicos estão
em `execution_summary.filters`; o horário do painel corresponde ao do agregado.

Os parâmetros novos `started_from`/`started_to` aceitam instantes com fuso e
reutilizam os limites inclusivos UTC. `source`, `file_type`, `status`,
`outcome`, `lifecycle` legado e `execution_id` também são suportados. Esses predicados são aplicados a execuções, Workorders, quantidades
e pendências da resposta, preservando as regras de publicação dos resultados.
As consultas `/indicators/{entity}` aceitam os mesmos parâmetros e continuam
aplicando a interseção entre `dashboard.read` e a permissão da entidade.

`date_from`/`date_to` legados do painel e de suas consultas relacionadas
continuam aceitando datas civis com a semântica anterior do fuso da sessão
PostgreSQL. O adaptador declara os limites correspondentes em UTC no agregado.
Não misturar qualquer parâmetro de data legada com qualquer limite de instante:
isso retorna `422 ambiguous_execution_period`. O cliente atualizado deve
converter os dias no fuso do perfil para instantes e enviar apenas a forma nova.

As leituras de catálogo, agregado e indicadores usam `REPEATABLE READ READ ONLY`;
cartões e agrupamentos não recebem versões diferentes dentro dessa resposta.
Chamadas HTTP separadas têm instantes próprios, declarados em `generated_at`.

### Consumo web

Visão geral, catálogo, detalhe e Modo TV usam `outcome` para apresentar a
situação. Duplicatas, canceladas e desconhecidas possuem categorias próprias.
O catálogo e o TV consultam página e `/executions/summary` com os mesmos filtros
e publicam o par somente após ambas as respostas concluírem. Totais, categorias
e fontes vêm exclusivamente do agregado, inclusive quando existem mais de 25
execuções. O TV identifica a lista como execuções recentes (até seis) dentro do
recorte total. Cada fonte mostra “Execuções desta fonte no período exibido”,
volume e participação sobre o mesmo denominador; fontes nulas possuem grupo próprio.

A navegação entre painel, catálogo, detalhe (retorno) e TV conserva os filtros
canônicos na URL. Datas civis usam o fuso do perfil, horários locais ambíguos
exigem um instante explícito e o fim do dia conserva precisão de microssegundos.
O escopo e os filtros efetivos acompanham os dados. Atualizações são publicadas
por conjunto completo; falhas mantêm o conjunto anterior com aviso, e perda de
permissão o remove. Um período inválido não é descartado para consultar um
conjunto mais amplo. Chamadas de página/resumo continuam tendo instantes próprios,
sem promessa de snapshot único entre requisições HTTP distintas.

Exemplo resumido do catálogo:

```json
{
  "items": [],
  "pagination": {"page": 1, "page_size": 20, "total": 0, "pages": 0},
  "sort": "newest",
  "generated_at": "2026-10-22T20:00:00Z"
}
```

O [relatório de reconciliação da #193](execution-reconciliation-validation.md)
relaciona critérios de aceite, comandos, massa sintética e capturas dos três
recortes, incluindo falhas de atualização, escopos e zoom nativo.

## Demonstração sintética

Com a API e o PostgreSQL iniciados, o script gera as massas, importa as quatro fontes,
captura o identificador criado e consulta todo o acompanhamento:

```bash
API_URL=http://localhost:8000 scripts/demo_execution_monitoring.sh
```

O roteiro remove a massa temporária ao terminar e não exige rede corporativa ou RPA.
A coleção reproduzível para clientes HTTP está em
[`docs/http/execution-monitoring.http`](http/execution-monitoring.http).
