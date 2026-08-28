# Consolidação de Workorders

O serviço `app.consolidation.consolidate` cruza registros que já passaram pela
validação e normalização. Ele não altera as fontes, não aplica regras OQC e não
toma decisões automáticas.

## Entrada e correspondência

Cada registro informa `source`, `execution_id`, `source_file_id`, `sheet`,
`row` e o objeto `values`. A Workorder é resolvida nesta ordem:

1. `workorder_number` presente no próprio registro;
2. relação única previamente observada por `demand_id`;
3. relação única previamente observada por `serial_number`;
4. relação única previamente observada por `lot_number`.

Relações ambíguas não são escolhidas silenciosamente. O registro permanece
fora da consolidação com `unmatched_record`, e a chave recebe
`ambiguous_relationship`.

Mesmo quando o registro informa `workorder_number`, Demand ID, serial e lote
são comparados com todas as relações observadas. Se qualquer identificador
também estiver associado a outra Workorder, os registros contraditórios não
entram em nenhuma Workorder e recebem `conflicting_relationship`. A ocorrência
preserva a proveniência, a chave conflitante e todas as Workorders relacionadas.

## Quantidades

Registros da mesma fonte e Workorder são somados. Quando mais de uma fonte
informa o mesmo indicador, o valor consolidado usa a precedência abaixo e os
totais divergentes continuam registrados em `source_divergence`:

| Indicador | Precedência |
| --- | --- |
| Planejada | N-FP, GMES/OQC, OWM, TMS |
| Produzida | GMES/OQC, N-FP, OWM, TMS |
| Recebida, liberada, pendente e hold | OWM, GMES/OQC, TMS, N-FP |

A quantidade pendente é o maior valor entre a pendência explícita e
`planejada - liberada`, nunca menor que zero, quando os dois operandos estão
presentes. Quantidades ausentes permanecem `null`: ausência de liberação, por
exemplo, não equivale a uma liberação igual a zero. A quantidade em hold usa o valor
explícito `retained_quantity` e pode contar seriais marcados explicitamente com
`hold_flag=true` ou estado `hold`/`retained`. Um estado `rejected` não é
convertido em hold, pois essa classificação pertence às regras da etapa
seguinte.

`partially_released` é verdadeiro somente quando a quantidade liberada é maior
que zero e menor que a recebida. Se uma dessas quantidades estiver ausente, o
resultado também permanece `null`.

## Integração ao pipeline

`app.processing.process_normalized_records` aceita somente registros cujo
`execution_id` seja igual ao da execução em processamento. O pipeline fornece
diretamente os objetos gerados pela normalização; XLSX, CSV e JSON não são
reabertos nesta etapa. Uma falha de conteúdo em uma Workorder gera
`workorder_processing_failed` e não impede a consolidação das demais.

O endpoint de importação pode receber vários pares `source`/`file` no mesmo
pedido. O repositório reserva todos os arquivos sob um único `execution_id` e
devolve seus IDs antes do processamento. Assim, a precedência e a detecção de
divergências usam o caminho real da API, e não apenas chamadas diretas ao
serviço em memória.

Exemplo de proveniência de um campo consolidado:

```json
{
  "source": "N-FP",
  "execution_id": "exec-2026-001",
  "source_file_id": 2,
  "sheet": "Plano",
  "row": 7,
  "field": "planned_quantity",
  "value": 10
}
```

## Auditoria e reprodutibilidade

Existe uma única saída por Workorder. Cada campo contém sua lista de
`provenance`, com fonte, execução, arquivo, aba, linha, nome do campo e valor.
`selected_quantity_sources` identifica a fonte efetivamente usada para cada
total e `calculations` registra fórmula e entradas de todos os valores derivados.
Uma proveniência repetida com o mesmo conteúdo é ignorada e registrada como
`duplicate_record_ignored`; conteúdos diferentes com a mesma proveniência
interrompem a consolidação, pois não podem ser auditados com segurança.
As entradas e saídas são ordenadas por chaves estáveis; a ordem dos arquivos de
entrada não altera o resultado.

Workorders sem as quatro fontes são marcadas como `incomplete` e listam
`missing_sources`. Diferenças de Demand ID, modelo, organização, tipo, lote por
serial ou quantidade entre fontes são preservadas como ocorrências, sem
sobrescrever os dados observados.

## Comparação com a planilha de referência

`compare_with_reference` compara os seis indicadores quantitativos por
Workorder e relata ausências ou diferenças. A massa controlada está em:

- `data/synthetic/consolidation_records.json`;
- `data/synthetic/wo-status-reference.csv`.

Ela cobre Workorders normal, PQ e PM, correspondência completa e inexistente,
quantidade e liberação parciais, serial sem correspondência, container com
serial retido e divergências de lote e organização.
