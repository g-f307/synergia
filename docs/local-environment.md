# Reconstrução do ambiente local

O procedimento abaixo reconstrói a fundação desde um clone e um PostgreSQL 16
vazio. Os exemplos usam apenas dados sintéticos do repositório.

## Pré-requisitos

- Git;
- Docker com Docker Compose;
- cliente `psql` 16 no `PATH` ou o `psql` do container Docker;
- Python 3.11 ou superior;
- Node.js compatível com `frontend-angular/package.json` (22.12 é usado na CI);
- Google Chrome para os testes Angular headless.

Confirme as ferramentas:

```text
git --version
docker compose version
# opcional quando o cliente estiver instalado no host
psql --version
python --version
node --version
npm --version
```

## 1. Clone e configuração

```bash
git clone https://github.com/g-f307/synergia.git
cd synergia
git switch main
git pull --ff-only origin main
```

No PowerShell:

```powershell
Copy-Item .env.example .env
$env:DATABASE_URL = "postgresql://synergia:synergia-local-only@localhost:5432/synergia"
$env:PGHOST = "localhost"
$env:PGPORT = "5432"
$env:PGDATABASE = "synergia"
$env:PGUSER = "synergia"
$env:PGPASSWORD = "synergia-local-only"
```

Em shell POSIX:

```bash
cp .env.example .env
export DATABASE_URL=postgresql://synergia:synergia-local-only@localhost:5432/synergia
export PGHOST=localhost PGPORT=5432 PGDATABASE=synergia
export PGUSER=synergia PGPASSWORD=synergia-local-only
```

As credenciais acima são exclusivamente locais e já constam no exemplo. Nunca
versione `.env` real. O FastAPI não carrega `.env` automaticamente: exporte
`DATABASE_URL` no terminal em que iniciar a API.

Variáveis opcionais:

- `IMPORT_STORAGE_DIR`: diretório controlado; o padrão é `data/imports/`;
- `VALID_ORGANIZATION_CODES`: códigos oficiais separados por vírgula.

## 2. PostgreSQL vazio e migrations

O comando seguinte remove o volume local deste Compose. Faça isso somente para
uma reconstrução descartável; ele apaga o banco local existente.

```bash
docker compose down --volumes
docker compose up -d postgres
docker compose ps
docker compose exec -T postgres pg_isready -U synergia -d synergia
```

Aguarde o serviço ficar saudável e aplique todas as migrations em ordem desde a
raiz do repositório:

```bash
python scripts/validate_project_assets.py
```

O script usa as variáveis `PG*`, executa cada arquivo de
`database/migrations/` com `ON_ERROR_STOP` e também valida todas as massas
sintéticas. Quando `psql` não existe no host, ele usa automaticamente o cliente
do serviço `postgres` do Compose. Deve ser usado em banco vazio; migrations
publicadas não são reescritas nem reaplicadas sobre um schema já criado.

Confirme o schema:

```bash
docker compose exec -T postgres psql -U synergia -d synergia \
  -c "SELECT table_name FROM information_schema.tables WHERE table_schema = 'synergia' ORDER BY table_name;"
```

## 3. Backend

PowerShell:

```powershell
Set-Location backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest -q -m "not integration"
.\.venv\Scripts\python.exe -m pytest -q -m integration tests
.\.venv\Scripts\python.exe -m compileall -q app
Set-Location ..
```

Shell POSIX:

```bash
cd backend
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
ruff check .
pytest -q -m "not integration"
pytest -q -m integration tests
python -m compileall -q app
cd ..
```

Os testes de integração usam `DATABASE_URL` e pressupõem migrations aplicadas.

## 4. Frontend Angular

```bash
cd frontend-angular
npm ci
npm run lint
npm test -- --watch=false --browsers=ChromeHeadless --code-coverage
npm run build
cd ..
```

Se a política de execução do PowerShell bloquear `npm.ps1`, use `npm.cmd` nos
mesmos comandos, por exemplo `npm.cmd ci` e `npm.cmd run build`.

`npm ci` usa exatamente o lockfile. O endereço local da API fica em
`frontend-angular/src/environments/environment.ts`.

## 5. Iniciar a aplicação

Em um terminal, com `DATABASE_URL` exportada:

```powershell
Set-Location backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Em outro terminal:

```powershell
Set-Location frontend-angular
npm start
```

- Angular: <http://localhost:4200>
- FastAPI: <http://localhost:8000>
- OpenAPI: <http://localhost:8000/docs>

Valide a saúde:

```bash
curl http://localhost:8000/health
```

Resultado esperado:

```json
{"status":"ok","service":"synergia-api"}
```

## 6. Importação sintética e consulta

PowerShell, a partir da raiz:

```powershell
$response = curl.exe -sS -X POST http://localhost:8000/imports `
  -F "source=N-FP" `
  -F "imported_by=ambiente.local" `
  -F "file=@data/synthetic/n-fp_minimal.csv"
$executionId = ($response | ConvertFrom-Json).execution_id
$response
curl.exe -sS "http://localhost:8000/imports/$executionId"
curl.exe -sS "http://localhost:8000/imports/$executionId/validation-report"
curl.exe -sS "http://localhost:8000/imports/$executionId/normalized-data"
```

Shell POSIX:

```bash
curl -sS -X POST http://localhost:8000/imports \
  -F 'source=N-FP' \
  -F 'imported_by=ambiente.local' \
  -F 'file=@data/synthetic/n-fp_minimal.csv'
curl -sS http://localhost:8000/imports/<execution_id>
curl -sS http://localhost:8000/imports/<execution_id>/validation-report
curl -sS http://localhost:8000/imports/<execution_id>/normalized-data
```

Substitua `<execution_id>` pelo valor retornado com HTTP `201`. A consulta deve
mostrar uma execução concluída ou `validation_failed` de forma rastreável; para
a massa mínima válida, o relatório não deve conter erro impeditivo.

## 7. Equivalência com a CI

Antes de abrir PR, confirme ainda:

```bash
docker compose config
git diff --check
git status --short
```

A CI repete os testes/builds em Linux, cria PostgreSQL 16 vazio, aplica todas as
migrations, valida dados e verifica a branch `prototype-pages`. Não altere o
protótipo durante este procedimento.
