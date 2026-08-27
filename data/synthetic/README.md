# Arquivos sintéticos

Os arquivos na raiz são exemplos mínimos válidos para cada fonte. O diretório
`invalid/` contém entradas deliberadamente inválidas; elas são evidências de
teste e jamais devem ser usadas como base para corrigir dados de origem.

| Arquivo inválido | Fonte usada no teste | Cenário |
| --- | --- | --- |
| `missing-required-column.csv` | N-FP | cabeçalho obrigatório ausente/alterado |
| `empty-data.csv` | N-FP | arquivo sem linhas de dados |
| `invalid-values.csv` | N-FP | Workorder ausente, quantidade e data inválidas, organização desconhecida |
| `duplicate-serial.csv` | OWM | serial duplicado |
| `formula-errors.csv` | N-FP | `#VALUE!` e referência `#REF!` preservados |
| `unmatched-key.csv` | TMS | chave de Workorder sem correspondência |

Uma linha inteiramente vazia é registrada como aviso. Erros de estrutura,
campos, tipos, fórmulas, identificadores e relacionamentos são impeditivos.
O relatório produzido ao lado do original contém arquivo, aba, linha, coluna,
severidade, código e motivo de cada ocorrência.
