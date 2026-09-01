# SYNERGIA API

Backend FastAPI inicial. A implementação começa sem RPA e utilizará arquivos
manuais e dados sintéticos como fontes de entrada.

## Autenticação

A API implementa access token JWT, refresh opaco rotativo e revogação de
sessões. O adaptador local fica desabilitado por padrão e é proibido em
produção; configuração, contratos e exemplos estão em
[`../docs/authentication.md`](../docs/authentication.md).

## Execução prevista

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

Execute os testes com `pytest`.

## Importação rastreável

Configure a conexão e, opcionalmente, o diretório controlado de evidências:

```bash
export DATABASE_URL=postgresql://synergia:synergia-local-only@localhost:5432/synergia
export IMPORT_STORAGE_DIR=/var/lib/synergia/imports
# O padrão é 25 MiB e 24 horas de retenção para rejeitados
export UPLOAD_MAX_BYTES=26214400
export UPLOAD_REJECTED_RETENTION_HOURS=24
# Opcional: catálogo oficial, separado por vírgulas
export VALID_ORGANIZATION_CODES=ORG-001,LG
```

Envie XLSX, CSV ou JSON informando uma das fontes permitidas e o usuário (ou
`technical_origin`, para uma execução técnica):

```bash
curl -X POST http://localhost:8000/imports \
  -F 'source=N-FP' \
  -F 'imported_by=operador.local' \
  -F 'file=@entrada.csv'
```

Para consolidar fontes diferentes na mesma execução, repita `source` e `file`
na mesma ordem. Cada arquivo recebe seu próprio `source_file_id` antes da
normalização e todos os normalizados elegíveis seguem juntos para a consolidação:

```bash
curl -X POST http://localhost:8000/imports \
  -F 'source=N-FP' -F 'file=@plano.csv' \
  -F 'source=OWM' -F 'file=@recebimento.csv' \
  -F 'source=GMES/OQC' -F 'file=@qualidade.xlsx' \
  -F 'source=TMS' -F 'file=@embarque.json' \
  -F 'imported_by=operador.local'
```

A resposta `201` contém o `execution_id`. Consulte o estado sem acessar o
conteúdo do arquivo:

```bash
curl http://localhost:8000/imports/72a15cf7-f1d1-4df4-ad73-7a79ef98ae36
```

Cada arquivo aceito passa pelo esquema da fonte. Um erro impeditivo preserva o
arquivo e conclui a execução com `status=validation_failed`, impedindo que ela
seja usada pela consolidação. Avisos permanecem no relatório sem bloquear. Para
visualizar todas as ocorrências:

```bash
curl http://localhost:8000/imports/72a15cf7-f1d1-4df4-ad73-7a79ef98ae36/validation-report
```

O relatório também é preservado como `validation-report.json` no diretório da
execução. Cada ocorrência informa arquivo, aba, linha, coluna, severidade,
código e motivo. Erros de Excel (`#VALUE!`, `#REF!` etc.) são lidos com as
fórmulas habilitadas e nunca convertidos em zero. Exemplos inválidos e seu uso
estão documentados em `data/synthetic/README.md`.

A organização somente é classificada como desconhecida quando
`VALID_ORGANIZATION_CODES` está configurada. Sem um catálogo oficial, o campo
continua sujeito à validação de presença e formato, mas não é comparado com
nomes de sistemas ou com uma lista fixa.

Arquivos aprovados também geram `normalized-data.json`. O resultado mantém os
valores originais, os valores internos e a transformação aplicada por campo,
e pode ser consultado por:

```bash
curl http://localhost:8000/imports/72a15cf7-f1d1-4df4-ad73-7a79ef98ae36/normalized-data
```

Os registros são persistidos em `synergia.normalized_records`. O mapeamento de
colunas, estados e flags OQC está em `docs/normalization.md`.

## Pipeline integrado

O importador lê o arquivo uma única vez e entrega sua representação tabular ao
serviço `app.pipeline.run_pipeline`. A representação importada é validada em
memória; somente linhas sem erros impeditivos são normalizadas.
Erros de uma linha não interrompem linhas independentes, enquanto erros de
estrutura (por exemplo, coluna obrigatória ausente) bloqueiam o arquivo.

Importados, rejeições, avisos, normalizados, resumo e evento de auditoria são
confirmados em uma única transação. O vínculo rastreável é:

`execution_id → source_file_id → imported_record_id → normalized_record`

Cada registro também conserva aba, linha, valores originais e transformações.
Os normalizados elegíveis recebem o `execution_id` e o `source_file_id` reais e seguem, sem nova
leitura do original, para `app.processing.process_normalized_records`. Essa
etapa consolida Workorders, lotes, seriais e organizações e então executa o
catálogo versionado de regras. O resultado e seu resumo ficam no objeto
`processing` de `normalized-data.json`; sua persistência operacional definitiva
permanece fora desta etapa.
As contagens podem ser consultadas em
`GET /imports/{execution_id}/pipeline-summary`. Exemplo:

```json
{
  "rows_read": 3,
  "valid_records": 2,
  "rejected_records": 1,
  "normalized_records": 2,
  "errors": 1,
  "warnings": 1
}
```

Duplicidades por SHA-256 são reservadas atomicamente no PostgreSQL, retornam
`409` mesmo sob uploads concorrentes e indicam a execução original. Arquivo
vazio ou estruturalmente inválido retorna `422`, e extensão não suportada
retorna `415`. Todas essas respostas incluem um ID consultável quando a fonte
e o ator já foram aceitos.

O arquivo é recebido primeiro em `<IMPORT_STORAGE_DIR>/quarantine/` com nome
aleatório. Após extensão, MIME, tipo real, tamanho, magic bytes, ZIP e conteúdo
ativo serem aprovados, ele é movido byte a byte para
`<IMPORT_STORAGE_DIR>/accepted/<fonte>/<execution_id>/<token>.<extensão>`.
A API e os logs não expõem conteúdo, caminho absoluto nem nome interno.
Decisões seguras podem ser consultadas em
`GET /imports/{execution_id}/inspections`; formatos, limites e retenção estão em
[`../docs/upload-security.md`](../docs/upload-security.md). Em desenvolvimento,
o diretório padrão é `data/imports/`, ignorado pelo Git.

A especificação OpenAPI interativa está em `http://localhost:8000/docs` e o
documento JSON em `http://localhost:8000/openapi.json`.

## Consultas e reprocessamento

A API disponibiliza contratos para consultar execuções, Workorders, lotes,
seriais, pendências, histórico, resultado consolidado e indicadores. As listas
possuem filtros, ordenação determinística e paginação. Todas as falhas usam o
envelope padronizado `error`.

`POST /executions/{execution_id}/reprocess` cria uma nova tentativa assíncrona
(`202`) e preserva a execução anterior. Rotas, corpos, códigos HTTP, filtros e
exemplos estão em `../docs/api-contracts.md`.

## Consolidação

Registros normalizados podem ser cruzados pelo serviço
`app.consolidation.consolidate`. O resultado mantém uma única entrada por
Workorder, proveniência por valor, ausências e divergências. O algoritmo,
precedência das fontes e comparação com a massa equivalente à `WO Status.xlsx`
estão documentados em `docs/consolidation.md`. O pipeline chama esse serviço
automaticamente apenas com registros normalizados elegíveis da execução atual.

## Regras de negócio

O resultado consolidado pode ser classificado por
`app.business_rules.classify`. O motor mantém categorias simultâneas, fila ativa
por antiguidade, histórico por execução e a evidência de cada regra aplicada.
O catálogo e as decisões de classificação estão documentados em
`docs/business-rules.md`.
