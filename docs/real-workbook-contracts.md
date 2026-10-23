# Contratos dos workbooks reais de homologação

## Objetivo e estado

Este documento registra o contrato estrutural proposto para as famílias de
workbooks `WO Status` e `Total Decision`. A versão inicial é
`1.0.0-draft`, está vinculada à issue
[#137](https://github.com/g-f307/synergia/issues/137) e ainda depende das
confirmações listadas ao final.

As cópias fornecidas foram inspecionadas somente no ambiente local. Arquivos,
linhas, identificadores e valores reais não são versionados. O contrato
executável e sanitizado está em
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
420 mil tokens de erro de fórmula e 22 tabelas dinâmicas. Não foram encontrados
links externos no pacote. Isso caracteriza um workbook misto, não uma fonte
tabular única.

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
| `WO Status` / `NFP` | candidata mista, bloqueada até allowlist | N-FP | linha 3 / linha 4 | combina IDs e planejamento com grande volume de fórmulas e erros; somente colunas literais confirmadas poderão ser lidas |
| `WO Status` / `OWM SN` | candidata a fonte | OWM | linha 2 / linha 3 | relaciona Workorder, serial, lote OQC, pallet, localização e estado |
| `WO Status` / `LOT PENDING_OQC` | candidata a fonte | GMES/OQC | linha 3 / linha 4 | concentra holds, liberações, motivo, estado e datas |
| `WO Status` / `CTNR STATUS` | candidata a fonte | TMS | linha 1 / linha 2 | concentra container, carga, transporte, inspeção, Workorder e datas logísticas |
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

## Tipos e identidade propostos

| Fonte | Identidade mínima proposta | Tipos relevantes |
| --- | --- | --- |
| `NFP` | ao menos `demand_id` ou `workorder_number` | IDs e estados como texto; quantidades como decimal não negativo; datas como data local até confirmação do fuso |
| `OWM SN` | `serial_number` e ao menos `workorder_number` ou `lot_number` | IDs como texto; quantidades como inteiro não negativo; flags somente após catálogo confirmado |
| `LOT PENDING_OQC` | `workorder_number` e `status` | IDs/estado como texto; quantidades como decimal não negativo; datas como data/hora local pendente de fuso |
| `CTNR STATUS` | `container_number` | IDs/estado como texto; quantidades como decimal; datas logísticas permanecem campos distintos |
| `Total Decision` | ao menos um identificador OQC e um identificador de Workorder | IDs/resultados como texto; quantidades como decimal; datas e instantes não recebem timezone inventado |

Essas identidades são propostas conservadoras. Registros que não as atendam
devem ser rejeitados com código estável, sem publicar o valor original.

## Mapeamento inicial

### N-FP — aba `NFP`

| Origem | Campo canônico proposto | Estado |
| --- | --- | --- |
| `Demand ID` | `demand_id` | confirmado estruturalmente |
| `W/O` | `workorder_number` | inferido, validar semântica |
| `Model`, `Suffix` | `model`, `model_suffix` | inferido |
| `Line` | `production_line` | inferido |
| `Lot Qty` | `lot_quantity` | inferido |
| `Plant` | `organization_code` | pendente: confirmar se planta equivale ao escopo organizacional |
| `PST`, `Due Date`, `BOM Date` | datas específicas do domínio | pendente: não reduzir todas a uma única data |
| `W/O Status` | `status` | pendente: catálogo e precedência |
| `OQC Pass` | `oqc_pass_quantity` ou estado | pendente: tipo e unidade |
| `Comment1`, `Comment2` | observações restritas | proibido em logs; persistência depende de necessidade aprovada |

Colunas de bucket temporal, resultados calculados, totais e qualquer célula
com fórmula ou erro ficam fora da primeira versão.

### OWM — aba `OWM SN`

| Origem | Campo canônico proposto | Estado |
| --- | --- | --- |
| `Org` | `organization_code` | inferido |
| `W/O` | `workorder_number` | inferido |
| `Serial Number` | `serial_number` | inferido |
| `OQC Lot` | `lot_number` | inferido |
| `Pallet No`, `Pallet Qty` | `pallet_number`, `pallet_quantity` | inferido |
| `Model`, `Locator`, `Status` | `model`, `locator`, `status` | inferido |
| `OQC Pass`, `OQC Hold Flag` | `oqc_flag`, `hold_flag` | pendente: domínio dos valores |
| `REASON` | `reason` | restrito; validar catálogo e retenção |

### GMES/OQC — aba `LOT PENDING_OQC`

| Origem | Campo canônico proposto | Estado |
| --- | --- | --- |
| `WO` | `workorder_number` | inferido |
| `Prod Date`, `Status Change Date`, `Target Date` | datas específicas do domínio | inferido |
| `Reason`, `Hold Group Code`, `Status` | `reason`, `hold_group_code`, `status` | inferido; catálogo pendente |
| `Cause Dept.` | `responsible_area` | pendente |
| `Hold Qty`, `Release Qty` | `hold_quantity`, `released_quantity` | inferido |
| `Request User`, `Change User` | atores de auditoria | sensível; acesso restrito e logs mascarados |

### TMS — aba `CTNR STATUS`

| Origem | Campo canônico proposto | Estado |
| --- | --- | --- |
| `CTNR No`, `CTNR Status` | `container_number`, `container_status` | inferido |
| `Model`, `W/O` | `model`, `workorder_number` | inferido |
| `Load Plan Qty`, `Load Qty`, `Rmn Qty` | quantidades planejada, carregada e restante | inferido |
| `Load Plan Date`, `Loading Date`, `Load Confirm Date`, `Closing Date` | datas logísticas distintas | inferido |
| `Inspection No`, `Inspection Status` | identificação e estado da inspeção | inferido |
| transportadora, fornecedor, destino, booking e observações | dados logísticos restritos | persistência e exposição dependem de necessidade aprovada |

### GMES/OQC — `Total Decision`

O adapter deve compor nomes únicos para os cabeçalhos de duas linhas. Por
exemplo, `Total Decision` + `Result` torna-se
`total_decision_result`; `Approval` + `User` torna-se
`approval_user`.

| Origem | Campo canônico proposto | Estado |
| --- | --- | --- |
| `OQC ID`, `OQC_LOT_ID`, `Inspection ID` | identificadores OQC | pendente: definir chave e relação |
| `WO Name`, `WO_ID`, `WOID` | identificadores de Workorder | pendente: definir diferenças e precedência |
| `MODEL`, `Suffix`, `Line` | `model`, `model_suffix`, `production_line` | inferido |
| `Prod Date`, `Inspection Date` | `production_date`, `inspection_date` | inferido |
| `Total Decision / Result`, `Judge Date`, `Remark` | decisão, instante e justificativa | inferido; catálogo pendente |
| `Approval / Approval`, `Date`, `Remark` | aprovação, instante e justificativa | inferido; catálogo pendente |
| `Hold Qty`, `Up. Qty`, `RW Qty`, `Remain Qty` | quantidades distintas | inferido; validar valores negativos |
| `MANUAL_OWNER`, usuários de decisão, upload e aprovação | atores de auditoria | sensível; acesso restrito e logs mascarados |

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

1. Quais colunas literais da aba `NFP` constituem a fonte oficial e quais
   resultados calculados são apenas apoio visual?
2. `OWM SN` é a fonte de autoridade para a relação entre Workorder, serial,
   lote OQC e pallet?
3. Qual fonte prevalece quando `LOT PENDING_OQC`, `OWMS Hold` e `OWM SN`
   discordam sobre hold ou liberação?
4. Qual é a granularidade de `CTNR STATUS`: container, container + modelo,
   container + Workorder ou outra combinação?
5. Em `Total Decision`, qual identificador é a chave da inspeção e como
   `OQC ID`, `OQC_LOT_ID` e `Inspection ID` se relacionam?
6. Qual é a diferença entre `WO Name`, `WO_ID` e `WOID`?
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

## Próximas etapas

As issues de adapters e testes devem usar este contrato como entrada. Qualquer
resposta do cliente que altere uma chave, interpretação ou precedência exige
nova versão do contrato, atualização dos testes e registro na matriz de
rastreabilidade antes da liberação da ingestão real.
