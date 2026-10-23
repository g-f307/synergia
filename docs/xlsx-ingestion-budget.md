# Orçamento de recursos para planilhas XLSX

Este documento descreve como a admissão, a leitura, a validação e a
normalização de XLSX são limitadas por um orçamento explícito de recursos, e
como esse orçamento deve ser operado. O recebimento seguro e a quarentena
continuam descritos em [upload-security.md](upload-security.md).

## Princípios

- Nenhuma parte do pacote XLSX é carregada inteira em memória. A inspeção e a
  leitura percorrem o arquivo em blocos ou por eventos XML.
- Cada limite é configurável, tem um valor padrão e produz uma rejeição com
  código estável, limite, valor observado e orientação.
- Elevar um limite exige medição prévia
  ([`scripts/measure_xlsx_ingestion.py`](../scripts/measure_xlsx_ingestion.py)).
- Uma rejeição por capacidade nunca derruba o processo e nunca deixa registros
  parciais: a execução termina como `failed` com o código da rejeição.
- CSV e JSON mantêm o comportamento e os contratos anteriores.

## Onde cada etapa atua

| Etapa | O que faz | Memória |
| --- | --- | --- |
| Admissão (`upload_security`, `xlsx_package`) | percorre cada parte XML em blocos de 1 MiB, procura marcadores perigosos mesmo entre fronteiras de bloco, soma os bytes descompactados, executa `iterparse` das abas e aplica os limites de abas, linhas, colunas, células, fórmulas, dimensão declarada e tempo | constante em relação ao tamanho da aba |
| Abertura (`validation._read_xlsx`) | lista as abas autorizadas e lê no máximo 200 linhas por aba para localizar o cabeçalho | uma janela de 200 linhas |
| Leitura (`spreadsheet_reader.LazySheetRows`) | reabre o arquivo a cada passagem em modo somente leitura e entrega as linhas uma a uma, reaplicando linhas, colunas, células e tempo | uma linha |
| Validação | percorre as linhas guardando só um digest de 16 bytes por linha para detectar duplicidade e interrompe ao exceder o orçamento de ocorrências | proporcional ao número de linhas, não às células |
| Normalização | gera os registros normalizados (ver "Memória dos registros") | proporcional às linhas e células aceitas |
| Consolidação e regras (`processing`) | agrupa por Workorder e classifica; consulta o relógio a cada 256 Workorders | ver "Memória dos registros" |

Cada arquivo é lido em três passagens (validação, registros importados e
normalização). O relógio de processamento reinicia por arquivo, antes da
primeira passagem; a admissão e a consolidação têm relógios próprios, todos
sob `INGESTION_MAX_SECONDS`.

## Limites

Todos aceitam sufixo da fonte (`_N_FP`, `_OWM`, `_GMES_OQC`, `_TMS`), que tem
precedência sobre o valor global. Valores ausentes usam o padrão; valores
não numéricos ou menores ou iguais a zero tornam a configuração inválida.

| Variável | Padrão | Aplica-se a |
| --- | --- | --- |
| `INGESTION_MAX_SHEETS` | 64 | todas as abas do pacote |
| `INGESTION_MAX_ROWS` | 1.048.576 | maior índice de linha de cada aba processada |
| `INGESTION_MAX_COLUMNS` | 16.384 | maior coluna de cada aba processada |
| `INGESTION_MAX_CELLS` | 2.000.000 | soma das células das abas processadas e da área declarada em `<dimension>` |
| `INGESTION_MAX_FORMULAS` | 2.000.000 | soma das fórmulas das abas processadas |
| `INGESTION_MAX_MEMORY_BYTES` | 1.073.741.824 | estimativa de memória do pipeline completo (ver "Memória dos registros") |
| `INGESTION_MAX_SECONDS` | 300 | admissão, leitura/normalização e consolidação, cada uma com relógio próprio |
| `INGESTION_MAX_ISSUES` | 250.000 | ocorrências de validação e normalização por arquivo e por execução |
| `INGESTION_PROGRESS_INTERVAL` | 10.000 | linhas entre eventos de progresso |
| `INGESTION_ALLOWED_SHEETS` | **nenhuma** | nomes de abas separados por `\|`, sem diferenciar maiúsculas; `*` autoriza todas |

Os limites de arquivo compactado continuam em `UPLOAD_MAX_BYTES`,
`UPLOAD_MAX_ARCHIVE_ENTRIES`, `UPLOAD_MAX_ARCHIVE_UNCOMPRESSED_BYTES` e
`UPLOAD_MAX_COMPRESSION_RATIO`
([upload-security.md](upload-security.md#formatos-e-limites)).

### Abas autorizadas

A seleção **falha fechada**: com `INGESTION_ALLOWED_SHEETS` ausente ou vazio,
nenhuma aba é autorizada e todo XLSX é rejeitado com `no_authorized_sheet`. Somente
as abas listadas são abertas, contadas e entregues ao pipeline; `*` é uma
autorização explícita de todas as abas, destinada a dados sintéticos e a
ambientes controlados (`.env.example`, testes e E2E a utilizam). Em homologação,
liste as abas do contrato. As demais abas:

- não consomem os orçamentos de linhas, colunas, células e fórmulas;
- continuam sujeitas à varredura de segurança (fórmulas perigosas, macros,
  vínculos externos, objetos incorporados), porque fazem parte do arquivo;
- continuam contando para os limites de bytes descompactados, de entradas e de
  tempo, pois precisam ser percorridas.

Se nenhuma aba do arquivo constar da lista, a rejeição também é
`no_authorized_sheet`. O contrato versionado de fontes e abas está em
[real-workbook-contracts.md](real-workbook-contracts.md); os adapters que o
aplicam são entregues em issues próprias.

### Dimensão declarada

O openpyxl completa com linhas vazias tudo o que a tag `<dimension>` declara.
Por isso a área declarada (`linhas × colunas`) é verificada antes de percorrer
a aba e uma dimensão como `A1:XFD1048576` é rejeitada sem ser iterada.

## Códigos de rejeição

Rejeições da admissão ficam em `GET /imports/{execution_id}/inspections`
(`reason_code`) e em `audit_events`. Todas retornam `details.guidance` e, quando
aplicável, `details.limit`, `details.observed` e `details.sheet`.

| Código | HTTP | Quando |
| --- | --- | --- |
| `workbook_sheet_limit` | 413 | mais abas que `INGESTION_MAX_SHEETS` |
| `workbook_row_limit` | 413 | aba com linha acima de `INGESTION_MAX_ROWS` |
| `workbook_column_limit` | 413 | aba com coluna acima de `INGESTION_MAX_COLUMNS` |
| `workbook_cell_limit` | 413 | células acima de `INGESTION_MAX_CELLS` |
| `workbook_dimension_limit` | 413 | área declarada acima de `INGESTION_MAX_CELLS` |
| `workbook_memory_limit` | 413 | estimativa de memória do pipeline acima de `INGESTION_MAX_MEMORY_BYTES` |
| `workbook_formula_limit` | 413 | fórmulas acima de `INGESTION_MAX_FORMULAS` |
| `no_authorized_sheet` | 422 | lista de abas ausente, vazia ou sem correspondência no arquivo |
| `ingestion_time_limit` | 422 | admissão ou processamento acima de `INGESTION_MAX_SECONDS` |
| `ingestion_issue_limit` | 422 | ocorrências acima de `INGESTION_MAX_ISSUES` |
| `unreadable_workbook` | 422 | arquivo ilegível durante a leitura |
| `archive_too_many_entries`, `archive_uncompressed_limit`, `archive_compression_ratio` | 422 | limites de arquivo compactado (inalterados) |

Exemplo:

```json
{
  "error": {
    "code": "workbook_row_limit",
    "message": "Aba com linhas acima do limite",
    "details": {
      "execution_id": "...",
      "guidance": "Divida a aba em arquivos menores ou solicite aumento medido do limite.",
      "limit": 5,
      "observed": 21,
      "sheet": "Dados"
    }
  }
}
```

### Limpeza e nova tentativa

Quando o orçamento é excedido durante o processamento, o serviço remove os
artefatos do pipeline e o original aceito, apaga a reserva do arquivo e a
reserva de idempotência da execução (`abort_claim`) e finaliza a execução como
`failed` com o código. Nada é persistido em `normalized_records`. Reenviar o
mesmo arquivo depois de ajustar o orçamento cria uma nova execução, sem ser
tratado como duplicidade. A inspeção e o motivo permanecem auditáveis.

## Progresso e métricas

Logs estruturados (`app/observability/telemetry.py`):

- `ingestion.progress`: `source`, `operation` (`reading`, `validating`,
  `importing`, `normalizing`), `processed_count` e `duration_ms`, a cada
  `INGESTION_PROGRESS_INTERVAL` linhas;
- `ingestion.completed` e `ingestion.rejected`: `source`, `reason_code`,
  `processed_count`, `rejected_count`, `duration_ms` e `peak_memory_bytes`.

Métricas Prometheus:

- `synergia_ingestion_duration_seconds{outcome}` (`completed`, `rejected`,
  `failed`);
- `synergia_ingestion_rows_total{result}` (`processed`, `rejected`);
- `synergia_ingestion_rejections_total{reason}`, com os códigos desta tabela e
  `other`;
- `synergia_ingestion_peak_memory_bytes`: pico de memória residente do
  processo (`ru_maxrss`), registrado ao final de cada ingestão. É uma marca
  d'água do processo, não o consumo isolado do arquivo.

As métricas e os eventos `ingestion.completed`/`ingestion.rejected` também
medem arquivos CSV e JSON; o progresso por fase e os limites de recursos
aplicam-se somente a XLSX.

Nenhum nome de aba, nome de arquivo ou valor de célula é registrado.

## Memória dos registros

A leitura e a validação não retêm a planilha, mas os registros importados e
normalizados são o resultado do pipeline: a consolidação por Workorder precisa
de todos eles, e cada registro guarda valores originais, normalizados e uma
transformação por célula. Por isso um limite apenas de células não protege
planilhas estreitas com muitas linhas: o custo fixo por linha domina.

O orçamento usa uma estimativa de memória do **pipeline completo**
(`IngestionBudget.estimated_memory`):

```text
bytes = linhas × custo_da_linha + células × 320
custo_da_linha = 22.000 abaixo de 50.000 linhas; 4.500 a partir de 50.000
```

O limiar de 50.000 acompanha `RULE_DETAIL_DEFER_THRESHOLD`: a partir dele o
pipeline não retém o detalhe das regras e o custo por linha cai, o que torna a
estimativa não monotônica (o pior caso está logo abaixo do limiar). Durante a
leitura só o custo mínimo (4.500 por linha) interrompe cedo, porque o total de
linhas ainda é desconhecido; a estimativa exata é aplicada com os totais ao
final da admissão e de cada passagem. Com três colunas, o limite padrão (1 GiB) admite cerca de 47 mil linhas no
regime caro e cerca de 196 mil no regime barato, menos se as células forem
muito largas; a consolidação consulta o relógio a cada 256
Workorders.

## Medições

Ambiente: Ubuntu 24.04, Python 3.12, openpyxl 3.1, 7 GiB de RAM. Os valores
variam com a máquina; use o script para repetir.

### Sintético reproduzível

`python scripts/measure_xlsx_ingestion.py --synthetic-rows N --columns 20`
com `INGESTION_MAX_CELLS` e `UPLOAD_MAX_BYTES` elevados:

| Linhas | Células | Descompactado | Admissão | Abertura | Validação | Normalização | Pico RSS (base 50 MiB) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 10.000 | 200.000 | 11,9 MB | 1,1 s | 0,6 s | 2,8 s | 3,1 s | 120 MB |
| 50.000 | 1.000.000 | 61,0 MB | 5,5 s | 3,2 s | 14,2 s | 16,4 s | 398 MB |

Nesta tabela só entram admissão, abertura, validação e normalização: o custo
marginal é de cerca de 350 bytes por célula aceita. Planilhas estreitas, com
muitas linhas, custam mais por célula; veja o pipeline completo abaixo.

### Pipeline completo (`run_pipeline`)

Pico de RSS acima da base do processo, medido com
`INGESTION_ALLOWED_SHEETS='*'` e `source=OWM`, três colunas (Workorder, serial,
status):

| Linhas | Workorders | Tempo | RSS acima da base | Por linha | Estimativa do orçamento |
| --- | --- | --- | --- | --- | --- |
| 10.000 | 10.000 | 49 s | 201 MB | 20,1 KB | 230 MB |
| 10.000 | 500 | 3,9 s | 148 MB | 14,8 KB | 230 MB |
| 30.000 | 1.000 | 12,4 s | 439 MB | 14,6 KB | 689 MB |
| 60.000 | 2.000 | 16,5 s | 228 MB | 3,8 KB | 328 MB |
| 100.000 | 5.000 | 31,8 s | 380 MB | 3,8 KB | 546 MB |

Com duas colunas (`N-FP`), 10.000 linhas de Workorders distintos: 188 MB, abaixo
da estimativa de 226 MB. O caso mais caro é o de muitos Workorders distintos,
que também é o mais lento: o laço de classificação filtra as ocorrências por
Workorder, o que cresce de forma quadrática. Esse custo é anterior a esta
entrega e não foi alterado; o relógio da consolidação garante apenas que ele
seja interrompido pelo orçamento de tempo.

### Workbook representativo (`WO Status`)

Arquivo de 41,5 MB com 17 abas e 471 MB descompactados, executado somente em
ambiente local autorizado. Nenhum valor é registrado.

| Cenário | Resultado |
| --- | --- |
| implementação anterior (`e910bfa`), limite de memória virtual de 1,4 GiB | `MemoryError` durante a admissão, com 1,38 GiB de RSS em 8,8 s |
| limites padrão | rejeitado em menos de 1 s por `archive_uncompressed_limit` (471 MB > 250 MiB), com 49 MiB de RSS |
| `UPLOAD_MAX_ARCHIVE_UNCOMPRESSED_BYTES=600000000` sem lista de abas | rejeitado por `workbook_dimension_limit` (área declarada de `NFP` = 2.352.296 > 2.000.000) |
| mesmo limite de memória de 1,4 GiB e `INGESTION_ALLOWED_SHEETS="CTNR STATUS"` | admitido em cerca de 23 s com 45 MiB de RSS no pico |

A abertura do workbook pelo openpyxl carrega a tabela de strings
compartilhadas inteira e acrescentou cerca de 155 MiB nesse arquivo; esse custo
é proporcional às strings do pacote, não à aba lida, e está limitado pelo
orçamento de bytes descompactados.

Esta entrega não valida nem normaliza os valores do workbook real: os adapters
por fonte dependem das respostas do cliente registradas em
[real-workbook-contracts.md](real-workbook-contracts.md). O leitor genérico não
reconhece, por exemplo, o cabeçalho de `CTNR STATUS` e informa `invalid_header`.

## Procedimento para ajustar um limite

1. Reproduza o caso com `scripts/measure_xlsx_ingestion.py`, em ambiente
   controlado e com uma aba por vez (`INGESTION_ALLOWED_SHEETS`).
2. Registre duração por fase e pico de memória; compare com
   `estimated_memory` (22.000 ou 4.500 bytes por linha mais 320 por célula).
3. Aumente apenas o limite que bloqueou, preferencialmente com o sufixo da
   fonte, e confirme que a memória do contêiner comporta o novo pico.
4. Registre a decisão e a medição no PR que alterar o valor padrão.

## Limitações conhecidas

- Os registros importados e normalizados continuam materializados até a
  consolidação e a persistência atômica; o orçamento de memória os mantém
  limitados, mas o consumo não é constante.
- A estimativa é calibrada no ambiente descrito abaixo e em formas de dados
  medidas; planilhas com formato muito diferente exigem nova medição.
- O tempo da consolidação cresce de forma quadrática com o número de
  Workorders distintos; o orçamento de tempo apenas o interrompe.
- O cabeçalho é procurado nas primeiras 200 linhas de cada aba.
- O openpyxl mantém as strings compartilhadas do pacote em memória.
- O progresso é emitido em logs e métricas; não há consulta de progresso na API.
- O pico de memória é do processo, não do arquivo.
