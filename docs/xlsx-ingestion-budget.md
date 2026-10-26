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
| Consolidação e regras (`processing`) | valida registros, consolida, classifica e agrega; consulta o relógio nos laços de validação de registros, de indexação, resolução e consolidação (a cada 1.024 registros, inclusive dentro de um único Workorder) e de classificação (a cada 256 Workorders e a cada 1.024 fatos de um Workorder) | ver "Memória dos registros" |

Cada arquivo é lido em três passagens (validação, registros importados e
normalização). A admissão tem um relógio próprio. Depois dela, o processamento usa um **único
relógio por execução**, compartilhado por todos os arquivos, por todas as abas de
um mesmo arquivo e pela consolidação; vale o menor `INGESTION_MAX_SECONDS` entre as
fontes participantes.

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
| `INGESTION_MAX_MEMORY_BYTES` | 1.073.741.824 | estimativa de memória do pipeline completo, por execução (ver "Memória dos registros") |
| `INGESTION_MAX_OPEN_BYTES` | 33.554.432 (32 MiB) | bytes descompactados de `sharedStrings.xml`, `styles.xml`, `workbook.xml` e temas, carregados inteiros na abertura |
| `INGESTION_MAX_FILES` | 10 | arquivos por requisição (global, sem sufixo de fonte) |
| `INGESTION_MAX_SECONDS` | 300 | admissão (relógio próprio) e, depois, leitura, normalização e consolidação da execução (relógio único) |
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

### Fontes compostas

Para a fonte `WO Status`, a lista de abas padrão é a do contrato do adapter
(`INGESTION_ALLOWED_SHEETS_WO_STATUS` a restringe) e os orçamentos de células,
fórmulas e memória contam somente as colunas que o adapter mantém, não a largura
da aba. Veja [wo-status-adapters.md](wo-status-adapters.md#limites-da-fonte).

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
| `workbook_metadata_limit` | 413 | partes carregadas na abertura acima de `INGESTION_MAX_OPEN_BYTES` |
| `ingestion_file_limit` | 413 | mais arquivos que `INGESTION_MAX_FILES`, rejeitado antes de qualquer processamento |
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
  `processed_count`, `rejected_count`, `duration_ms` e
  `estimated_memory_bytes`.

Métricas Prometheus:

- `synergia_ingestion_duration_seconds{outcome}` (`completed`, `rejected`,
  `failed`);
- `synergia_ingestion_rows_total{result}` (`processed`, `rejected`);
- `synergia_ingestion_rejections_total{reason}`, com os códigos desta tabela e
  `other`;
- `synergia_ingestion_estimated_memory_bytes`: estimativa da última ingestão
  XLSX calculada por `IngestionBudget.estimated_memory`;
- `synergia_ingestion_memory_budget_bytes`: limite aplicado à mesma ingestão.
  Resultados anteriores ao pipeline e execuções sem orçamento XLSX zeram ambos
  os valores, evitando combinar medições de execuções diferentes.

Todo caminho terminal de uma ingestão registra um resultado: limite de arquivos
por requisição, rejeição na admissão, arquivo ilegível (`invalid_file`),
rejeição durante o processamento (inclusive limite de tempo na consolidação),
falha de armazenamento ou inesperada (`failed`) e conclusão. Validações de
requisição anteriores à ingestão (fontes ausentes, nomes duplicados, permissão)
e duplicidades por hash não são resultados de ingestão. Em uma execução com vários arquivos,
cada arquivo registra a duração capturada ao fim da própria fase, sem somar os
arquivos seguintes nem a consolidação, e o resultado terminal da execução; o
motivo da rejeição é contado uma vez por execução. As rejeições da admissão
registram a duração até a decisão. As métricas e os eventos
`ingestion.completed`, `ingestion.rejected` e `ingestion.failed` também medem
arquivos CSV e JSON; o progresso por fase e os limites de recursos aplicam-se
somente a XLSX.

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
bytes = registros_normalizados × custo_do_registro + células × 320
custo_do_registro = 22.000 abaixo de 50.000 registros; 4.500 a partir de 50.000
```

O limiar de 50.000 é o mesmo de `RULE_DETAIL_DEFER_THRESHOLD`, que decide se o
pipeline retém o detalhe das regras. Por isso a estimativa usa a **mesma
cardinalidade** do pipeline — os registros normalizados de toda a execução — e
não as linhas físicas do arquivo, que incluem cabeçalho, preâmbulo e linhas
vazias, inválidas ou rejeitadas. Um workbook de 50.000 linhas físicas com
cabeçalho gera, no máximo, 49.999 registros e permanece no regime caro. A
estimativa não é monotônica: o pior caso está logo abaixo do limiar.

A verificação ocorre em três momentos:

1. **Admissão e leitura:** o total de registros ainda é desconhecido, então só se
   aplica o limite inferior (`minimum_memory`, 4.500 bytes por linha física mais
   320 por célula), válido para qualquer contagem final. Ele interrompe cedo
   planilhas que não caberiam nem no regime barato.
2. **Acúmulo da execução:** como todos os arquivos de uma requisição alimentam as
   mesmas listas de registros, o limite inferior também é verificado sobre os
   totais acumulados a cada arquivo.
3. **Antes da consolidação:** com todos os arquivos normalizados, a estimativa
   exata é aplicada ao total de registros e células da execução. Vários arquivos
   individualmente abaixo do limite são, portanto, rejeitados quando somados
   (`workbook_memory_limit`, sem `sheet`). Execuções só com CSV ou JSON não têm
   orçamento e mantêm o comportamento anterior.

Quando uma execução reúne fontes com limites diferentes (sufixos `_N_FP`, `_OWM`,
`_GMES_OQC`, `_TMS`), valem em conjunto os **menores** limites de memória, tempo
e ocorrências (`INGESTION_MAX_ISSUES`, comparado ao total acumulado) entre as fontes participantes, de modo que o resultado não depende
da ordem dos arquivos no `multipart`.

Com três colunas, o limite padrão (1 GiB) admite cerca de 47 mil registros no
regime caro e cerca de 196 mil no regime barato, menos se as células forem muito
largas. A consolidação consulta o relógio a cada 256 Workorders.

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
| 10.000 | 10.000 | 27 s | 203 MB | 20,3 KB | 230 MB |
| 10.000 | 500 | 3,9 s | 148 MB | 14,8 KB | 230 MB |
| 30.000 | 1.000 | 12,5 s | 440 MB | 14,7 KB | 689 MB |
| 60.000 | 2.000 | 16,5 s | 228 MB | 3,8 KB | 328 MB |
| 100.000 | 5.000 | 31,8 s | 380 MB | 3,8 KB | 546 MB |

Com duas colunas (`N-FP`), 10.000 linhas de Workorders distintos: 188 MB, abaixo
da estimativa de 226 MB. O caso mais caro é o de muitos Workorders distintos, que
também é o mais lento. A busca de ocorrências por Workorder era quadrática e
passou a usar um agrupamento único (49 s para 27 s neste caso); o tempo restante
cresce com os Workorders distintos e é limitado pelo relógio da consolidação.

### Workbook representativo (`WO Status`)

Arquivo de 41,5 MB com 17 abas e 471 MB descompactados, executado somente em
ambiente local autorizado. Nenhum valor é registrado.

| Cenário | Resultado |
| --- | --- |
| implementação anterior (`e910bfa`), limite de memória virtual de 1,4 GiB | `MemoryError` durante a admissão, com 1,38 GiB de RSS em 8,8 s |
| limites padrão | rejeitado em menos de 1 s por `archive_uncompressed_limit` (471 MB > 250 MiB), com 49 MiB de RSS |
| `UPLOAD_MAX_ARCHIVE_UNCOMPRESSED_BYTES=600000000` sem lista de abas | rejeitado por `workbook_dimension_limit` (área declarada de `NFP` = 2.352.296 > 2.000.000) |
| mesmo limite de memória de 1,4 GiB e `INGESTION_ALLOWED_SHEETS="CTNR STATUS"` | admitido em cerca de 23 s com 45 MiB de RSS no pico |

Ao abrir o workbook, o openpyxl carrega inteiros, antes de ler qualquer linha,
as strings compartilhadas, os estilos e a definição do workbook. Nesse arquivo
essas partes somam 17,4 MiB descompactados (4,8 de strings e 12,6 de estilos) e a
abertura acrescentou cerca de 155 MiB de RSS em 6,7 s, aproximadamente 9 bytes
de memória por byte de XML. Esse custo independe da aba lida e por isso tem
orçamento próprio (`INGESTION_MAX_OPEN_BYTES`, verificado pelo cabeçalho do ZIP na
admissão e novamente antes de cada abertura).

As medições acima pertencem à entrega original da #138, anterior aos adapters.
WO Status e Total Decision agora possuem adapters próprios (#139/#140), com
políticas conservadoras para as respostas ainda pendentes do cliente. O leitor
genérico continua sem reconhecer os cabeçalhos dessas famílias. O corpus e as
medições integradas atualizadas estão em
[ingestion-corpus-validation.md](ingestion-corpus-validation.md).

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
- O tempo da consolidação ainda cresce mais que linearmente com o número de
  Workorders distintos; o orçamento de tempo o interrompe.
- O cabeçalho é procurado nas primeiras 200 linhas de cada aba.
- O openpyxl carrega estilos e strings compartilhadas inteiros na abertura; o
  orçamento de metadados limita esse custo, mas ele continua proporcional ao tamanho
  dessas partes (cerca de 9 bytes por byte de XML no workbook medido).
- O progresso é emitido em logs e métricas; não há consulta de progresso na API.
- A métrica operacional é uma estimativa do modelo de orçamento, não uma medida
  do RSS do processo. Ajustes do modelo exigem nova medição controlada.
