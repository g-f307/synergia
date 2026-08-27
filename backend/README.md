# SYNERGIA API

Backend FastAPI inicial. A implementação começa sem RPA e utilizará arquivos
manuais e dados sintéticos como fontes de entrada.

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
```

Envie XLSX, CSV ou JSON informando uma das fontes permitidas e o usuário (ou
`technical_origin`, para uma execução técnica):

```bash
curl -X POST http://localhost:8000/imports \
  -F 'source=N-FP' \
  -F 'imported_by=operador.local' \
  -F 'file=@entrada.csv'
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

Duplicidades por SHA-256 são reservadas atomicamente no PostgreSQL, retornam
`409` mesmo sob uploads concorrentes e indicam a execução original. Arquivo
vazio ou estruturalmente inválido retorna `422`, e extensão não suportada
retorna `415`. Todas essas respostas incluem um ID consultável quando a fonte
e o ator já foram aceitos.

O arquivo aceito é preservado byte a byte em
`<IMPORT_STORAGE_DIR>/<fonte>/<execution_id>/original.<extensão>`. A API e os
logs não expõem seu conteúdo nem o caminho absoluto. Em desenvolvimento, o
diretório padrão é `data/imports/`, ignorado pelo Git.

A especificação OpenAPI interativa está em `http://localhost:8000/docs` e o
documento JSON em `http://localhost:8000/openapi.json`.
