# Contratos dos workbooks reais de homologação

## Objetivo e estado

Este documento registra o contrato estrutural proposto para as famílias de
workbooks `WO Status` e `Total Decision`. A versão inicial é
`1.1.0-draft`, está vinculada à issue
[#137](https://github.com/g-f307/synergia/issues/137) e ainda depende das
confirmações listadas ao final.

As cópias fornecidas foram inspecionadas somente no ambiente local. Arquivos,
linhas, identificadores e valores reais não são versionados. A representação
legível por máquina e sanitizada do contrato está em
[`real-workbook-contracts-v1.json`](real-workbook-contracts-v1.json).

## Princípios de ingestão

- A política é **negar por padrão**: aba ou coluna não permitida pelo adapter
  não entra na normalização.
- Fórmulas, células com erro, totais, pivôs, filtros analíticos e visões
  derivadas não se tornam fonte operacional silenciosamente.
- Identificadores permanecem texto; ausência não vira zero e uma relação não é
  inventada.
- Cabeçalhos compostos são resolvidos pelo adapter antes da normalização.
- Campos de usuário, observações e partes comerciais recebem minimização,
  controle de acesso e mascaramento em logs e evidências.
- Cada linha aceita registra, no mínimo, hash SHA-256 do arquivo, aba, linha
  física e versão do adapter.

## Evidência estrutural sanitizada

As duas cópias recebidas de `WO Status` são idênticas byte a byte. A família
possui 17 abas, aproximadamente 1,57 milhão de células com fórmulas, mais de
420 mil ocorrências de tokens de erro (aproximadamente 228 mil células com
resultado de erro), 11 tabelas dinâmicas e quatro caches de pivot. Não foram
encontrados links externos no pacote. Isso caracteriza um workbook misto, não
uma fonte tabular única.

`OWM SN` concentra aproximadamente 1,38 milhão dessas fórmulas e mais de 220
mil células com resultado de erro. A dimensão física de uma aba não pode,
portanto, ser tratada automaticamente como quantidade de registros.

`Total Decision` possui uma aba, 554 linhas e 74 colunas, sem fórmulas, links
externos ou tabelas dinâmicas. Seu cabeçalho ocupa duas linhas, a terceira linha
é um resumo de totais e os registros começam na quarta linha.

Essas contagens descrevem apenas a estrutura observada e não constituem dados
operacionais.

## Decisão por aba

As classificações têm significados distintos: **confirmado estruturalmente** é
o que foi observado sem interpretar o negócio; **inferido** é uma proposta de
mapeamento; **pendente** exige resposta do cliente; **ignorado** não participa
da ingestão; e **proibido** não pode ser copiado para logs, fixtures ou
evidências. Nenhuma inferência equivale a aceite do cliente.

| Família / aba | Decisão inicial | Destino | Cabeçalho / dados | Justificativa |
| --- | --- | --- | --- | --- |
| `WO Status` / `NFP` | candidata mista, bloqueada até allowlist | N-FP | linha 3 / linha 4 | combina IDs e planejamento com grande volume de fórmulas, erros e cabeçalhos espelhados; exige seletor por coluna e validação do cabeçalho |
| `WO Status` / `OWM SN` | candidata mista | OWM | linha 2 / linha 3 | relaciona Workorder, serial, lote OQC e pallet, mas `Org` e `REASON` são calculados e a cauda da aba é preenchida apenas por fórmulas |
| `WO Status` / `LOT PENDING_OQC` | candidata mista, bloqueada | GMES/OQC | linha 3 / linha 4 | somente 18 linhas demonstram estado e quantidades; os identificadores dessas linhas dependem de fórmula e não podem ser promovidos |
| `WO Status` / `CTNR STATUS` | candidata a fonte limitada | TMS | linha 1 / linha 2 | demonstra container, modelo, quantidades e datas logísticas; Workorder e inspeção estão vazios na amostra |
| `WO Status` / `Mercosul` | auxiliar pendente | nenhum | não aplicável | aba oculta e sem proprietário ou semântica confirmados |
| `WO Status` / `Analysis 2` | ignorada | nenhum | não aplicável | visão analítica derivada; não é fonte de verdade |
| `WO Status` / `Analysis NPI` | ignorada | nenhum | não aplicável | visão analítica derivada; não é fonte de verdade |
| `WO Status` / `Planilha2` | auxiliar pendente | nenhum | não aplicável | estrutura intermediária sem contrato confirmado |
| `WO Status` / `OWMS Hold` | pendente, excluída | possível OWM/OQC | não aplicável | sobrepõe informações de hold existentes em fontes candidatas; precedência desconhecida |
| `WO Status` / `RWOK LOCATOR` | auxiliar pendente | possível OWM | não aplicável | lookup de localização/retrabalho sem chave e precedência confirmadas |
| `WO Status` / `RWOK LOCATOR (2)` | auxiliar pendente | possível OWM | não aplicável | segunda variante do lookup sem chave ou precedência confirmadas |
| `WO Status` / `VESSEL DEAD LINE` | auxiliar pendente | possível TMS | não aplicável | agenda logística sem confirmação de autoridade ou granularidade |
| `WO Status` / `ICMS` | ignorada | nenhum | não aplicável | visão fiscal/analítica fora do contrato operacional inicial |
| `WO Status` / `Analysis QTY` | ignorada | nenhum | não aplicável | aba oculta com resultado analítico derivado |
| `WO Status` / `OTD1` | ignorada | nenhum | não aplicável | visão analítica derivada; não é fonte de verdade |
| `WO Status` / `Sales` | ignorada | nenhum | não aplicável | visão comercial derivada e fora do contrato operacional inicial |
| `WO Status` / `Master` | auxiliar pendente | nenhum | não aplicável | possível lookup sem proprietário ou regra de precedência confirmados |
| `Total Decision` / `Sheet1` | candidata a fonte | GMES/OQC | linhas 1 e 2 / linha 4 | registros literais de inspeção, decisão, aprovação e quantidades; linha 3 é total e deve ser descartada |

Uma aba classificada como candidata ainda permanece desabilitada até que seu
adapter específico seja implementado e testado. Abas ignoradas ou pendentes
não podem ser processadas pelo leitor genérico.

## Cobertura observada e limitações

As contagens abaixo são agregadas da amostra local. Elas não autorizam copiar
valores nem garantem que arquivos futuros terão a mesma cobertura.

| Fonte | Janela observada | Cobertura relevante | Limitação contratual |
| --- | --- | --- | --- |
| `NFP` | 8.309 linhas após o cabeçalho | U/Y/AM têm 8.309 valores literais; JV tem 4.672; `W/O` em IE tem 5.678 (68,3%) | G/I/L são espelhos diretos por fórmula; M é uma coluna calculada de mesmo nome; nenhuma delas pode ser selecionada; `W/O` não é obrigatório em toda linha |
| `OWM SN` | 93.495 linhas físicas | `Serial Number` e `W/O` têm 60.070 valores literais; `OQC Lot`, 44.722 | cerca de 33 mil linhas finais existem por causa de fórmulas; `Org` e `REASON` são 100% calculados |
| `LOT PENDING_OQC` | intervalo físico de 130 linhas (4–133), com 91 linhas materializadas no arquivo | 88 linhas têm campos predefinidos, mas apenas 18 têm `Status`, grupo, datas e quantidades operacionais | nas 18 linhas substantivas, `WO` e `Reason` dependem de fórmula; `Cause Dept.`, `Target Date` e `Change User` não têm evidência |
| `CTNR STATUS` | 398 linhas | container, estado, modelo e quantidades têm 398 valores literais | `W/O`, `Inspection No` e `Inspection Status` estão vazios nas 398 linhas |
| `Total Decision` | 551 linhas | `WO Name`, `WO_ID`, `OQC_LOT_ID`, `ORG_ID` e quantidades têm 551 valores literais | `Inspection ID`, `WOID` e todo o bloco `Approval` estão vazios |

## Seleção determinística

O adapter não pode resolver cabeçalhos apenas pelo texto. Cada coluna permitida
é identificada por letra, linha e texto esperado. Qualquer deslocamento ou
divergência de cabeçalho interrompe a ingestão com erro de contrato. Uma coluna
com fórmula ou erro é rejeitada mesmo quando o nome esperado coincide.

Em `NFP`, os seletores iniciais são U (`Plant`), Y (`Demand ID`), AM
(`Lot Qty`) e JV (`OQC Pass`). G, I, L e M apresentam os mesmos nomes somente
em colunas de fórmula e estão proibidas: G, I e L são referências diretas a U,
Y e AM; M é uma coluna calculada de mesmo nome, não um espelho direto de JV. A
confirmação do cliente ainda é necessária para declarar as quatro colunas
literais como fontes oficiais.

Em `Total Decision`, o caminho de cabeçalho multinível e a letra da coluna
formam o seletor. Cabeçalhos repetidos como `C`, `Not in 6 Months`, `Result` e
`User` não recebem sufixo automático nem são autorizados por coincidência; uma
ocorrência precisa estar explicitamente listada no contrato.

## Tipos e identidade propostos

| Fonte | Identidade mínima proposta | Tipos relevantes |
| --- | --- | --- |
| `NFP` | ao menos `demand_id` ou `workorder_number` | IDs e estados como texto; quantidades como decimal não negativo; datas como data local até confirmação do fuso |
| `OWM SN` | `serial_number` e `workorder_number`; organização vem do contexto autorizado da execução até confirmação de fonte literal | IDs como texto; quantidades como inteiro não negativo; flags somente após catálogo confirmado |
| `LOT PENDING_OQC` | indefinida: o adapter permanece bloqueado enquanto a chave das 18 linhas substantivas depender de fórmula | IDs/estado como texto; quantidades como decimal não negativo; datas como data/hora local pendente de fuso |
| `CTNR STATUS` | `container_number` | IDs/estado como texto; quantidades como decimal; datas logísticas permanecem campos distintos |
| `Total Decision` | `oqc_lot_id` e ao menos `workorder_number` ou `workorder_id`; `ORG_ID` é candidato ao escopo organizacional | IDs/resultados como texto; quantidades como decimal; datas e instantes não recebem timezone inventado |

Essas identidades são propostas conservadoras. Registros que não as atendam
devem ser rejeitados com código estável, sem publicar o valor original.

## Mapeamento inicial

### N-FP — aba `NFP`

| Origem | Campo canônico proposto | Estado |
| --- | --- | --- |
| Y / `Demand ID` | `demand_id` | literal em 8.309 linhas; fonte oficial pendente de confirmação |
| IE / `W/O` | `workorder_number` | literal em 5.678 linhas; opcional na amostra e semântica pendente |
| `Model`, `Suffix` | `model`, `model_suffix` | inferido |
| `Line` | `production_line` | inferido |
| AM / `Lot Qty` | `lot_quantity` | literal em 8.309 linhas; unidade pendente |
| U / `Plant` | `plant` | literal em 8.309 linhas; preservada sem semântica de organização até o cliente confirmar se planta equivale ao escopo organizacional |
| `PST`, `Due Date`, `BOM Date` | datas específicas do domínio | pendente: não reduzir todas a uma única data |
| `W/O Status` | `status` | pendente: catálogo e precedência |
| JV / `OQC Pass` | `oqc_pass_quantity` ou estado | literal em 4.672 linhas; tipo e unidade pendentes |
| `Comment1`, `Comment2` | observações restritas | proibido em logs; persistência depende de necessidade aprovada |

G / `Plant`, I / `Demand ID` e L / `Lot Qty` são espelhos diretos por fórmula;
M / `OQC Pass` é uma coluna calculada de mesmo nome. As quatro ficam proibidas.
Colunas de bucket temporal, resultados calculados, totais e qualquer célula
com fórmula ou erro também ficam fora da primeira versão.

### OWM — aba `OWM SN`

| Origem | Campo canônico proposto | Estado |
| --- | --- | --- |
| `W/O` | `workorder_number` | inferido |
| `Serial Number` | `serial_number` | inferido |
| `OQC Lot` | `lot_number` | inferido |
| `Pallet No`, `Pallet Qty` | `pallet_number`, `pallet_quantity` | inferido |
| `Model`, `Locator`, `Status` | `model`, `locator`, `status` | inferido |
| `OQC Pass`, `OQC Hold Flag` | `oqc_flag`, `hold_flag` | pendente: domínio dos valores |
| `Org` | nenhum | proibida: 93.495 fórmulas; organização deve vir do contexto autorizado da execução até existir fonte literal confirmada |
| `REASON` | nenhum | proibida: 93.495 fórmulas; motivo operacional permanece indisponível nesta fonte |

O fim dos dados é a última linha com `Serial Number` literal. Linhas posteriores
preenchidas somente por fórmulas são ignoradas. Uma lacuna dentro da região
ativa continua sendo rejeitada e registrada, não convertida em linha vazia.

### GMES/OQC — aba `LOT PENDING_OQC`

| Origem | Campo canônico proposto | Estado |
| --- | --- | --- |
| `Hold Group Code`, `Status` | `hold_group_code`, `status` | literais nas 18 linhas substantivas; catálogo pendente |
| `Status Change Date` | `status_changed_at` | literal nas 18 linhas substantivas; fuso pendente |
| `Hold Qty`, `Release Qty` | `hold_quantity`, `released_quantity` | inferido |
| `Request User` | ator de auditoria | sensível; acesso restrito e logs mascarados |
| `WO`, `Reason`, `Prod Date` | nenhum | bloqueados: as linhas substantivas dependem de fórmula; não há chave literal segura |
| `Cause Dept.`, `Target Date`, `Change User` | nenhum | sem evidência na amostra; negar até nova amostra e validação |

Uma linha é substantiva quando possui `Status` literal. As demais linhas
predefinidas não são rejeitadas como registros. O adapter desta aba permanece
desabilitado até o cliente indicar uma fonte literal para a chave e esclarecer
a relação com `OWMS Hold` e `OWM SN`.

### TMS — aba `CTNR STATUS`

| Origem | Campo canônico proposto | Estado |
| --- | --- | --- |
| `CTNR No`, `CTNR Status` | `container_number`, `container_status` | inferido |
| `Model` | `model` | literal em 398 linhas |
| `Load Plan Qty`, `Load Qty`, `Rmn Qty` | `load_planned_quantity`, `load_quantity`, `load_remaining_quantity` | inferido; nomes próprios para não competir com a precedência global de `planned_quantity` |
| `Load Plan Date`, `Loading Date`, `Load Confirm Date` | datas logísticas distintas | literais; cobertura varia por campo |
| `Closing Date` | nenhum | sem evidência na amostra; negar até nova amostra e validação |
| `W/O`, `Inspection No`, `Inspection Status` | nenhum | sem evidência nas 398 linhas; negar até nova amostra e validação |
| transportadora, fornecedor, destino, booking e observações | dados logísticos restritos | persistência e exposição dependem de necessidade aprovada |

### GMES/OQC — `Total Decision`

O adapter usa a letra e o caminho das duas linhas de cabeçalho. Por exemplo,
AK / `Total Decision` + `Result` torna-se `total_decision_result`. Ele não
inventa nomes únicos para cabeçalhos repetidos que não estejam autorizados.

| Origem | Campo canônico proposto | Estado |
| --- | --- | --- |
| C / `OQC ID`, BE / `OQC_LOT_ID` | identificadores OQC | literais; definir relação e precedência |
| J / `WO Name`, BF / `WO_ID` | identificadores de Workorder | literais; definir diferença e precedência |
| BM / `ORG_ID` | `organization_code` | preenchido em 551 linhas; confirmar se representa o escopo organizacional |
| `MODEL`, `Suffix`, `Line` | `model`, `model_suffix`, `production_line` | inferido |
| `Prod Date`, `Inspection Date` | `production_date`, `inspection_date` | inferido |
| `Total Decision / Result`, `Judge Date`, `Remark` | decisão, instante e justificativa | inferido; catálogo pendente |
| `Hold Qty`, `Up. Qty`, `RW Qty`, `Remain Qty` | quantidades distintas | inferido; validar valores negativos |
| BG / `Inspection ID`, BH / `WOID`, AS:AW / `Approval` | nenhum | sem evidência nas 551 linhas; negar até nova amostra e validação |
| AM / usuário da decisão, AR / usuário do upload | atores de auditoria | sensíveis; acesso restrito e logs mascarados |
| Z / `MANUAL_OWNER` | nenhum | sem evidência e sensível; negado intencionalmente |

## Proveniência e segurança

Cada registro aceito deve carregar:

- `source_file_sha256` e nome lógico sanitizado da fonte;
- `source_sheet` e `source_row` físicos;
- `adapter_id` e `adapter_version`;
- instante da ingestão e execução associada;
- cabeçalho original usado e transformações aplicadas;
- ocorrências de validação sem copiar o conteúdo sensível da célula.

O hash identifica o conteúdo, mas não autoriza sua divulgação. Nomes de
pessoas, contas, comentários, fornecedores, transportadoras, clientes,
destinos e referências comerciais não devem aparecer em logs, fixtures,
prints de CI ou mensagens de erro. Fixtures futuras devem ser inteiramente
sintéticas ou sanitizadas e possuir manifesto próprio.

## Questões para validação com o cliente

1. U/Y/AM/JV são as fontes oficiais de `Plant`, `Demand ID`, `Lot Qty` e
   `OQC Pass` em `NFP`? Os espelhos G/I/L e a coluna calculada M devem ser
   sempre descartados?
2. `OWM SN` é a fonte de autoridade para a relação entre Workorder, serial,
   lote OQC e pallet?
3. Qual fonte prevalece quando `LOT PENDING_OQC`, `OWMS Hold` e `OWM SN`
   discordam sobre hold ou liberação?
4. Qual é a granularidade de `CTNR STATUS`: container, container + modelo ou
   outra combinação? De qual fonte vêm Workorder e inspeção, ausentes nesta
   amostra?
5. Em `Total Decision`, qual identificador é a chave: `OQC ID` ou
   `OQC_LOT_ID`? De qual fonte vem `Inspection ID`, vazio nesta amostra?
6. Qual é a diferença entre `WO Name` e `WO_ID`? `WOID`, vazio nesta amostra,
   ainda será utilizado?
7. O que significam `M(S)`, `M(O)`, `C`, `Poss.`, `Sp. Qty` e `Mac Qty`?
8. Quais campos de usuário são necessários para auditoria e por quanto tempo
   podem ser retidos?
9. Qual fuso horário e quais formatos se aplicam às datas sem timezone?
10. Os arquivos são snapshots integrais ou deltas? Qual é a chave de
    idempotência entre versões?
11. Erros de fórmula observados são esperados? Valores calculados podem ser
    usados ou devem ser sempre descartados?
12. Quais observações e dados comerciais podem ser persistidos e exibidos por
    perfil?
13. `ORG_ID` de `Total Decision` representa o mesmo escopo organizacional usado
    pelo RBAC? Qual fonte literal deve fornecer a organização de `OWM SN`?
14. Cabeçalhos repetidos como `C` e `Not in 6 Months` possuem usos distintos ou
    devem ser descartados integralmente?

## Histórico do contrato

- `1.1.0-draft` (#139): `Plant` deixa de ser mapeada como `organization_code`
  (campo `plant`) e as quantidades de contêiner de `CTNR STATUS` recebem nomes
  próprios (`load_planned_quantity`, `load_quantity`, `load_remaining_quantity`),
  porque `planned_quantity` participa da precedência global de consolidação.
- `1.0.0-draft` (#137): contrato inicial.

Os adapters da família `WO Status` implementam este contrato e estão descritos em
[wo-status-adapters.md](wo-status-adapters.md).

## Próximas etapas

As issues de adapters e testes devem usar este contrato como entrada. Qualquer
resposta do cliente que altere uma chave, interpretação ou precedência exige
nova versão do contrato, atualização dos testes e registro na matriz de
rastreabilidade antes da liberação da ingestão real.
