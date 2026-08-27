# SYNERGIA

Sistema em desenvolvimento para automação e consolidação de indicadores de
suprimentos. A primeira etapa utiliza Angular, FastAPI, PostgreSQL, arquivos
manuais e dados sintéticos; integrações RPA serão incorporadas posteriormente.

## Estrutura

- `frontend-angular/`: aplicação web Angular;
- `backend/`: API FastAPI;
- `database/`: migrations e documentação do modelo persistente;
- `data/synthetic/`: massas sintéticas controladas;
- `docker-compose.yml`: PostgreSQL para desenvolvimento local.

## Protótipo navegável

O protótipo estático aprovado não é duplicado na `main`. Ele permanece em:

- branch `prototype-pages`;
- tag `prototype-v1.0`;
- GitHub Pages: <https://g-f307.github.io/synergia/>.

## Pré-requisitos

- Node.js 20.19, 22.12 ou versão posterior compatível com Angular 20;
- Python 3.11 ou superior;
- Docker com Docker Compose.

## PostgreSQL

```bash
docker compose up -d postgres
```

## Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

A API ficará disponível em `http://localhost:8000`; o endpoint de saúde é
`GET /health`. Uploads rastreáveis são feitos em `POST /imports` e consultados
em `GET /imports/{execution_id}`; exemplos e configuração estão em
`backend/README.md`.

Testes:

```bash
cd backend
pytest
```

## Frontend Angular

```bash
cd frontend-angular
npm install
npm start
```

O frontend ficará disponível em `http://localhost:4200` e consultará o endpoint
de saúde da API.

O endereço da API utilizado pelo Angular é definido em
`frontend-angular/src/environments/environment.ts`. O `.env` da raiz é
reservado aos serviços de backend e infraestrutura; aplicações Angular não
carregam esse arquivo automaticamente.

Build e testes:

```bash
cd frontend-angular
npm run build
npm test -- --watch=false
```

## Configuração

Copie `.env.example` para `.env` apenas no ambiente local. O arquivo `.env` é
ignorado pelo Git e não deve conter credenciais reais compartilhadas.

## Integração contínua

O workflow `.github/workflows/ci.yml` valida Pull Requests e pushes para
`main`. Ele executa lint, testes com relatórios e build do Angular e FastAPI,
valida migrations, dados sintéticos e Docker Compose e confirma, somente para
leitura, que o protótipo permanece disponível na branch `prototype-pages`.

As migrations SQL em `database/migrations/` são aplicadas, em ordem pelo nome,
em um PostgreSQL 16 temporário durante a CI. A validação falha quando não há
migrations ou quando qualquer arquivo contém SQL inválido para PostgreSQL.
Os dados sintéticos aceitos em
`data/synthetic/` são arquivos JSON válidos ou CSV com cabeçalho preenchido.
