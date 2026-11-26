# Quantidades conhecidas e cobertura dos indicadores — #196

Contrato aditivo da API **0.19.0**. A cobertura é calculada sobre as Workorders
atuais por `(executions.organization_id IAM, workorder_number)`, conforme a
[seleção da #195](workorder-snapshots.md). A organização importada é dado de
negócio, não autorização.

## Recorte e seleção

Somente execuções `completed`/`completed_with_errors`, com IAM conhecido e
visíveis ao ator, são elegíveis. Organização, período, fonte, tipo de arquivo,
estado/situação e execução são aplicados **antes** da janela que seleciona a
linha por `updated_at DESC, id DESC`.

Uma nova versão parcial substitui a anterior sem buscar valores antigos para
completar campos. Zero é um valor conhecido. A cobertura não infere aplicabilidade,
metas corporativas, qualidade do dado nem presença de determinada fonte.
Proveniência e cobertura das fontes por Workorder pertencem à #197.

O período usa o **início da execução**, com limites inclusivos. Instantes
`started_from`/`started_to` devem incluir fuso e são normalizados para UTC.
As datas legadas `date_from`/`date_to` mantêm o calendário do banco, sem poder
ser combinadas com os parâmetros de instantes.

## Campos novos em `GET /indicators`

- `workorders_current.total`: tamanho do conjunto atual autorizado.
- `workorders_current.partially_released`: quantidade de versões atuais cujo
  indicador persistido de liberação parcial é `true`; `null` não vira `true`.
- `quantities_coverage`: objetos obrigatórios para `planned`, `produced`,
  `received` e `released`, cada um com os campos abaixo.

| Campo | Regra |
| --- | --- |
| `known_sum: integer|null` | Soma dos valores não nulos; `null` se não houver valor conhecido |
| `known_count` | Workorders atuais com a quantidade informada, incluindo zero |
| `total_count` | Todas as Workorders atuais no recorte, sem pressupor aplicabilidade |
| `coverage_percent: number|null` | `100 * known_count / total_count`, sem arredondamento na API; `null` quando vazio |
| `state` | `complete`, `partial`, `missing` ou `empty`, conforme a tabela abaixo |

| Estado | Condição | Exemplo de um objeto de cobertura |
| --- | --- | --- |
| `partial` | `0 < known_count < total_count` | `{"known_sum":4,"known_count":2,"total_count":3,"coverage_percent":66.66666666666667,"state":"partial"}` |
| `complete` | `known_count = total_count > 0` | `{"known_sum":0,"known_count":3,"total_count":3,"coverage_percent":100,"state":"complete"}` |
| `missing` | `known_count = 0 < total_count` | `{"known_sum":null,"known_count":0,"total_count":3,"coverage_percent":0,"state":"missing"}` |
| `empty` | `total_count = 0` | `{"known_sum":null,"known_count":0,"total_count":0,"coverage_percent":null,"state":"empty"}` |

Para valores `4/null/0`, o subtotal é 4 e a cobertura é 2/3, inclusive quando
existe uma versão antiga completa do mesmo número. Somar outra versão ao total
ou promover um campo ausente a zero viola este contrato.

### Compatibilidade

`workorders` e `quantities` **não mudam de significado**. Continuam agregando os
snapshots históricos elegíveis no mesmo recorte; `quantities` permanece
all-or-nothing (um nulo torna o total daquela quantidade nulo). Clientes antigos
podem continuar lendo esses campos. Clientes novos devem usar os campos atuais
para apresentar cobertura, subtotais e o cartão/lista de Workorders atuais.
Se contagens antigas forem apresentadas, devem ser identificadas como histórico.

O agregado de execuções e as contagens de pendências preservam seus contratos.
As leituras compartilham a transação somente leitura/repeatable read do painel:
uma importação concorrente não troca a referência no meio da resposta.

## Listagem e reconciliação

`GET /indicators/workorders?view=current`:

- Reutiliza a mesma seleção atual do agregado; contagem e paginação ocorrem
  depois da seleção e compartilham um snapshot de leitura.
- Ordena por `updated_at DESC, snapshot_id DESC`, com desempate estável.
- Cada linha mantém `identifier`, `status`, `occurred_at` (início da execução),
  `execution_id`, `organization_id`, `snapshot_id` e `updated_at`; a seleção atual
  também informa `organization_name` IAM e `organization_code` importado.
- O detalhe deve receber `execution_id` e `organization_id` da linha escolhida.
- `view=history` permanece o default da API e preserva a listagem legada.
  `view=current` para `executions` ou `pending-items` retorna
  `422 workorder_selection_not_supported`; essas listas não mudam de semântica.

A resposta acrescenta `view` e `scope`:

```json
{
  "scope": {
    "permissions": ["dashboard.read", "business.read"],
    "organization_ids": ["19600000-0000-4000-8000-000000000001"]
  }
}
```

O escopo é calculado no servidor, após a interseção das permissões e a
organização solicitada. `organization_ids=null` indica acesso global IAM
conhecido; uma organização externa nunca é incorporada para fazer os totais
coincidirem. As outras entidades informam sua própria permissão específica.

### Permissões distintas

O painel usa `dashboard.read`, sem exigir `business.read` para consultar os
agregados. A listagem usa a interseção de `dashboard.read` e `business.read`.
Assim, os totais se reconciliam quando filtros e **escopos efetivos** coincidem,
conforme a #193. Se o ator tiver painel em A/B e detalhes apenas em A, o painel
pode agregar A/B e a lista mostra apenas A; o recorte distinto fica explícito
em `scope`, sem ocultar a diferença ou ampliar autorizações.

A ausência da permissão exigida e uma organização solicitada fora do escopo
retornam 403. Uma execução externa usada como filtro não revela seus registros:
o conjunto agregado/listado fica vazio. Leituras não alteram Workorders,
proveniência, histórico, aprovações, liberação ou relatórios emitidos.

## Apresentação no painel

O cartão **Workorders atuais** lê `workorders_current` e abre a lista com
`view=current`, mantendo os filtros da consulta bem-sucedida. A tela de detalhes
recebe a execução e a organização da versão selecionada; a lista mantém o modo,
os filtros e a página na URL. Uma URL explícita com `view=history` continua
disponível e apresenta o título de histórico.

**Quantidades e cobertura** apresenta, por quantidade:

- `complete`: total conhecido, X/Y Workorders e 100% de cobertura;
- `partial`: **Subtotal conhecido**, X/Y Workorders e percentual de cobertura;
- `missing`: **Não informado**, 0/Y Workorders, sem barra de quantidade;
- `empty`: **Sem Workorders no período**, sem quantidade ou percentual fictício.

As barras representam cobertura dos dados, nunca cumprimento de uma meta ou
comparação de grandezas. Zero conhecido permanece visível como zero informado.
O percentual é arredondado apenas na apresentação, conforme o idioma PT/EN;
o valor recebido da API permanece intacto. Ausência do novo contrato não é
preenchida pelos totais históricos.

Quando os detalhes têm escopo menor que o agregado, o cartão explicita essa
restrição e oferece **Ver Workorders autorizadas**. Sem permissão para os detalhes,
o agregado autorizado permanece visível e o cartão não oferece esse link.
A listagem apresenta o escopo efetivo informado pela API e cancela solicitações
anteriores quando os parâmetros mudam, limpando dados e contagens até a resposta.
