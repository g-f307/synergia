# Homologacao da planilha de referencia

## Resultado

A copia autorizada foi inspecionada somente no ambiente local. O arquivo real,
seu nome, seus valores e seus identificadores nao fazem parte do repositorio.
A compatibilidade estrutural foi incorporada por regras gerais, e uma fixture
equivalente, integralmente sintetica, comprova o fluxo reproduzivel.

## Inventario sanitizado

- dez abas operacionais tem cabecalho na linha 3;
- a aba de referencia tem cabecalho na linha 2;
- o contrato operacional contem lote, produto, linha, turno, status,
  responsavel, data e observacao;
- identificadores permanecem texto para preservar zeros a esquerda;
- nao foram encontrados formulas ou links externos na copia inspecionada.

O relatorio local contabilizou 479 linhas: dez datas invalidas e dois lotes
ausentes foram rejeitados por registro; onze linhas vazias e uma duplicidade
foram avisos. Nenhum valor de origem e emitido pelo relatorio.

A execucao completa usou um plano local autorizado para homologacao, com
Workorders pseudonimizadas e correlacao por lote. Esse plano temporario nao
representa cadastro operacional e nao foi versionado. O resultado sanitizado
esta em `docs/evidence/workbook-homologation-report.json`: 709 registros lidos,
697 normalizados, 12 rejeitados, 230 Workorders e 230 lotes consolidados, 174
classificacoes e 32 pendencias ativas.

## Decisoes de compatibilidade

1. O leitor procura o primeiro cabecalho reconhecivel em cada aba, sem depender
   de nome de arquivo ou numero fixo de linha.
2. A linha fisica acompanha validacao, normalizacao e proveniencia.
3. Qualidade pode apresentar Workorder ou Demand ID, lote ou serial. Relacoes
   ausentes ou conflitantes ficam explicitas e nao contaminam outra Workorder.
4. Colunas adicionais e valores originais sao preservados; ausencia nao vira zero.
5. Nao foram criadas excecoes para um arquivo especifico.

Sem uma fonte que relacione os identificadores a Workorders, a aplicacao nao
inventa essa relacao. A fixture inclui uma fonte N-FP sintetica correspondente.

## Seguranca e reproducao

O upload continua sujeito a extensao, MIME, assinatura, tamanho e quarentena.
Formulas, macros, objetos ativos e links seguem `upload_security`. O script emite
somente esquema, tipos, contagens e codigos de ocorrencia.

```powershell
python scripts/generate_homologation_fixture.py
python scripts/homologate_workbook.py `
  data/synthetic/fixtures/homologated-workbook/quality-reference.xlsx `
  --companion-plan data/synthetic/fixtures/homologated-workbook/plan-reference.csv
```

Para inspecionar uma copia autorizada sem publicar valores:

```powershell
python scripts/homologate_workbook.py $env:REFERENCE_WORKBOOK `
  --companion-plan $env:REFERENCE_PLAN `
  --output artifacts/workbook-homologation.json
```

`REFERENCE_PLAN` deve apontar para o plano autorizado de correlacao usado na
homologacao. O relatorio nunca inclui os identificadores ou valores das fontes.
