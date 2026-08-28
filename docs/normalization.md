# Normalização de dados importados

A normalização é executada somente após a validação não encontrar erros
impeditivos. Ela não altera o arquivo original e não cruza informações entre
fontes.

Os mapeamentos declarativos ficam em
`backend/app/model/normalization_rules.json`. O arquivo é validado durante a
inicialização e uma regra ausente, com tipo incorreto ou chave duplicada causa
falha explícita. Os algoritmos de transformação permanecem em Python.

## Campos internos

| Conceito | Nome interno | Exemplos de cabeçalho aceitos | Transformação |
| --- | --- | --- | --- |
| Workorder | `workorder_number` | `workorder`, `work order`, `wo` | texto, sem espaços, maiúsculas |
| Demand ID | `demand_id` | `demand`, `demand id`, `id demanda` | texto, sem espaços, maiúsculas |
| Serial | `serial_number` | `serial`, `serial no` | texto, sem espaços, maiúsculas |
| Lote | `lot_number` | `lot`, `lote` | texto, sem espaços, maiúsculas |
| Modelo | `model` | `model`, `modelo` | texto, sem espaços, maiúsculas |
| Organização | `organization_code` | `organization`, `organização`, `org` | texto, sem espaços, maiúsculas |
| Container | `container_number` | `container`, `número container` | texto, sem espaços, maiúsculas |
| Datas | nome canônico terminado em `_date` ou `_at` | `planned_date`, `received_at` | ISO 8601 |
| Estado | `status` | `status`, `state`, `estado`, `shipment status` | tabela de estados abaixo |
| Flag OQC | `oqc_flag` | `oqc`, `oqc flag`, `status oqc` | booleano |
| Flags de regra | `hold_flag`, `rework_flag`, `ship_block_flag`, `active` | nomes canônicos ou `ativo` | booleano |
| Responsáveis | `responsible_organization`, `responsible_area` | `organização responsável`, `área responsável` | texto preservado |

Identificadores permanecem como texto. Strings numéricas preservam zeros à
esquerda e valores recebidos em notação científica são expandidos para a
representação decimal textual.

## Mapeamento de estados

| Entradas equivalentes | Estado interno |
| --- | --- |
| `open`, `opened`, `aberto` | `open` |
| `pending`, `pendente` | `pending` |
| `in progress`, `em andamento` | `in_progress` |
| `approved`, `aprovado` | `approved` |
| `rejected`, `rejeitado` | `rejected` |
| `released`, `liberado` | `released` |
| `received`, `recebido` | `received` |
| `partially approved`, `partially_approved`, `parcialmente aprovado` | `partially_approved` |
| `not applicable`, `not_applicable`, `não aplicável` | `not_applicable` |
| `completed`, `complete`, `closed`, `concluído` | `completed` |
| `cancelled`, `canceled`, `cancelado` | `cancelled` |

Um estado fora da tabela é normalizado para `snake_case`, preservado no
registro e acompanhado pelo aviso `unknown_state`. Nenhuma equivalência é
inferida silenciosamente.

## Mapeamento de flags OQC

| Entradas equivalentes | Valor interno |
| --- | --- |
| `1`, `true`, `yes`, `y`, `sim`, `approved`, `aprovado` | `true` |
| `0`, `false`, `no`, `n`, `não`, `not applicable`, `n/a` | `false` |

Valores desconhecidos produzem `null` e o aviso `unknown_oqc_flag`.

## Exemplo

Entrada:

```csv
Work Order,Demand ID,planned_date,Estado,OQC
 wo - 001 ,000000000000000123,27/08/2026,Aberto,Sim
```

Trecho da saída:

```json
{
  "values": {
    "workorder_number": "WO-001",
    "demand_id": "000000000000000123",
    "planned_date": "2026-08-27",
    "status": "open",
    "oqc_flag": true
  },
  "original_values": {
    "workorder_number": " wo - 001 ",
    "demand_id": "000000000000000123",
    "planned_date": "27/08/2026",
    "status": "Aberto",
    "oqc_flag": "Sim"
  }
}
```

Cada registro também contém `source`, `sheet`, `row` e `transformations`. Cada
transformação informa campo interno, coluna de origem, valor original, valor
normalizado e operação aplicada.
