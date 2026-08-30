# Arquivos sintéticos

Os arquivos na raiz são exemplos mínimos válidos para cada fonte. O diretório
`invalid/` contém entradas deliberadamente inválidas; elas são evidências de
teste e jamais devem ser usadas como base para corrigir dados de origem.

| Arquivo inválido | Fonte usada no teste | Cenário |
| --- | --- | --- |
| `missing-required-column.csv` | N-FP | cabeçalho obrigatório ausente/alterado |
| `empty-data.csv` | N-FP | arquivo sem linhas de dados |
| `invalid-values.csv` | N-FP | Workorder ausente, quantidade e data inválidas; organização desconhecida quando o catálogo configurado não contém `UNKNOWN` |
| `duplicate-serial.csv` | OWM | serial duplicado |
| `consolidation_records.json` | todas | consolidação completa, parcial, inexistente, PQ, PM, lote e organização divergentes |
| `wo-status-reference.csv` | referência | resultado esperado equivalente à `WO Status.xlsx` para a massa sintética |
| `rules_scenarios.json` | consolidação | catálogo completo de classificações, fila ativa, histórico e divergência |
| `formula-errors.csv` | N-FP | `#VALUE!` e referência `#REF!` preservados |
| `unmatched-key.csv` | TMS | chave de Workorder sem correspondência |
| `database_example.json` | API e banco | execução, Workorder, lote e serial mínimos para consultas |

Uma linha inteiramente vazia é registrada como aviso. Erros de estrutura,
campos, tipos, fórmulas, identificadores e relacionamentos são impeditivos.
O relatório produzido ao lado do original contém arquivo, aba, linha, coluna,
severidade, código e motivo de cada ocorrência.

## Gerador reproduzível

`scripts/generate_synthetic_data.py` gera dados claramente fictícios para
N-FP, OWM, GMES/OQC e TMS. O algoritmo usa somente um gerador pseudoaleatório
local, seed configurável e calendário fixo; portanto não depende do relógio,
rede, banco ou estado global. Todos os identificadores começam com `SYN-` e os
arquivos declaram que não contêm informação real ou pessoal.

Os formatos canônicos reproduzem os contratos atuais: N-FP em XLSX, OWM e TMS
em JSON e GMES/OQC em CSV. `--formats all` também produz cada fonte nos três
formatos aceitos. O XLSX tem propriedades e ZIP normalizados para que duas
execuções equivalentes sejam idênticas inclusive em SHA-256.

```powershell
python scripts/generate_synthetic_data.py `
  --profile small `
  --scenario comprehensive `
  --seed 20260830 `
  --output artifacts/synthetic/small-comprehensive
```

O diretório de saída precisa estar vazio. O `manifest.json` registra versão do
gerador e do schema, seed, perfil, cenário, fontes, formatos, entidades,
contagens, SHA-256 de cada arquivo e resultados esperados. A própria geração
reabre os arquivos e valida o manifesto antes de concluir.

## Perfis

| Perfil | Workorders | Seriais | Uso sugerido |
| --- | ---: | ---: | --- |
| `minimal` | 4 | 12 | fixture versionada e teste rápido |
| `small` | 50 | 500 | desenvolvimento local e demonstração |
| `medium` | 1.000 | 12.000 | homologação funcional |
| `reference` | 6.800 | 88.000 | massa próxima ao volume de referência |

Somente as fixtures `minimal-valid` e `minimal-comprehensive` são versionadas.
Os demais perfis devem ser gerados em `artifacts/synthetic/`, diretório ignorado
pelo Git, e publicados como artefatos temporários quando necessário.

## Catálogo de cenários

| Cenário no manifesto | Evidência esperada |
| --- | --- |
| `fully_valid` | hierarquia Workorder, Demand ID, lote e serial consistente |
| `source_divergence` | quantidade planejada divergente entre fontes |
| `workorder_absent`, `lot_absent` | relacionamento incompleto ou sem correspondência |
| `invalid_serial`, `duplicate_serial` | formato inválido e duplicidade impeditiva |
| `unknown_organization` | organização fora do catálogo sintético |
| `partial_release` | parte da quantidade permanece pendente |
| `oqc_pending`, `oqc_hold`, `long_term_hold` | decisões e retenções de qualidade |
| `rework`, `ship_block` | retrabalho e bloqueio de expedição |
| `required_data_absent` | campo obrigatório ausente |
| `invalid_date_and_quantity` | tipo e data incompatíveis com o contrato |

Use `--scenario valid` para comprovar o fluxo completo sem rejeições e
`--scenario comprehensive` para a massa com erros e divergências intencionais.
Uma seed igual produz o mesmo conjunto lógico e os mesmos bytes; seeds distintas
preservam a estrutura e alteram valores gerados.
