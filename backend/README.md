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
