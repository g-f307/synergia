# Primeiros passos no SYNERGIA

Este roteiro sobe PostgreSQL, migrations, API FastAPI e aplicação Angular em
containers. Ele usa somente configuração e dados locais; não representa a
implantação corporativa da LG.

## 1. Pré-requisitos

- Git;
- Docker Engine com Docker Compose v2;
- portas `5432`, `8000` e `8080` disponíveis.

Clone o repositório e prepare a configuração:

```bash
git clone https://github.com/g-f307/synergia.git
cd synergia
cp .env.example .env
```

Os valores da `.env.example` são apenas locais. Antes de qualquer ambiente
compartilhado, altere senhas e chaves e use o mecanismo de secrets do destino.

## 2. Construir e iniciar

```bash
docker compose config
docker compose up -d --build
docker compose ps
```

O serviço `migrate` termina com código zero depois de aplicar as migrations.
Os demais serviços devem aparecer como `healthy`.

| Componente | Endereço local |
|---|---|
| Aplicação web | <http://localhost:8080> |
| API | <http://localhost:8000> |
| OpenAPI | <http://localhost:8000/docs> |
| Liveness | <http://localhost:8000/health/live> |
| Readiness | <http://localhost:8000/health/ready> |

Valide o conjunto automaticamente:

```bash
python scripts/smoke_containers.py
```

O script respeita `BACKEND_PORT`, `WEB_PORT` e `SYNERGIA_API_ORIGIN`. Também é
possível informar `--backend-url`, `--web-url` e `--expected-api-origin`.

## 3. Primeiro acesso e jornada inicial

A autenticação local permanece desabilitada por padrão. Ela só deve ser usada
em desenvolvimento ou homologação controlada, com identidade preparada por um
procedimento autorizado. Em produção, aguarde o contrato de identidade da LG.

Depois de autenticado com um usuário autorizado:

1. acesse **Importações**;
2. envie uma massa sintética de `data/synthetic/` com a fonte correspondente;
3. acompanhe validação, normalização e processamento;
4. consulte a execução, divergências e pendências;
5. gere ou consulte o relatório e registre a decisão humana quando aplicável.

Dados reais, credenciais corporativas e conectores RPA não devem ser usados
neste ambiente local.

## 4. Logs e diagnóstico

```bash
docker compose logs -f backend web
docker compose logs migrate
docker compose exec postgres pg_isready -U synergia -d synergia
docker compose exec backend id
```

- API viva e não pronta: confira PostgreSQL, migrations e volumes.
- Interface sem acessar a API: confira `SYNERGIA_API_ORIGIN` e
  `AUTH_ALLOWED_ORIGINS` na `.env`.
- `migrate` com erro de checksum: uma migration já publicada foi alterada; não
  edite o histórico, crie uma nova migration.
- Banco criado pelo Compose antigo, sem histórico de migrations: faça backup,
  identifique a última migration realmente aplicada e execute uma única vez:

  ```bash
  MIGRATION_BASELINE_THROUGH=0025_add_observability_correlation.sql \
    docker compose up -d
  ```

  Depois remova a variável. O processo valida o schema, registra somente até o
  limite e executa as migrations posteriores.
- Erro de porta ocupada: ajuste `POSTGRES_PORT`, `BACKEND_PORT` ou `WEB_PORT`.

## 5. Parar, atualizar e limpar

Parar sem apagar dados:

```bash
docker compose down
```

Atualizar código e imagens preservando volumes:

```bash
git pull --ff-only
docker compose build --pull
docker compose up -d
```

Limpeza destrutiva exclusivamente local:

```bash
docker compose down --volumes --remove-orphans
```

O último comando apaga banco, importações e avatares persistidos nos volumes.
Consulte também o [contrato de implantação](container-deployment.md) antes de
entregar imagens para outro ambiente.
