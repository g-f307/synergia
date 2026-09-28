# Contrato de implantação em containers

## Artefatos

| Imagem | Função | Processo | Usuário |
|---|---|---|---|
| `synergia-backend:<versão>` | API e migrations | Uvicorn ou `apply_migrations.py` | `10001:10001` |
| `synergia-web:<versão>` | Angular estático | Nginx na porta 8080 | `nginx` |
| `postgres:16-alpine` | banco local | PostgreSQL | imagem oficial |

O PostgreSQL em container é uma conveniência local. A LG pode fornecer banco
gerenciado, desde que seja PostgreSQL compatível e aceite as migrations.

## Configuração mínima por ambiente

| Tema | Local | LG/homologação/produção |
|---|---|---|
| Tags | `local` | versão imutável ou digest |
| Banco | Compose | endpoint e política definidos pela LG |
| Segredos | `.env` ignorado | secret manager corporativo |
| URL pública da API | `http://localhost:8000` | definida por DNS/ingress |
| CORS | `http://localhost:8080` | origem pública exata do frontend |
| TLS | fora do Compose | terminado no ingress/proxy corporativo |
| Storage | volume nomeado | volume persistente com backup |
| Logs | `stdout`/`stderr` | coletor corporativo |
| Identidade | local desabilitada | SSO/contrato aprovado |

Variáveis sensíveis obrigatórias fora do ambiente local incluem
`POSTGRES_PASSWORD`, `AUTH_JWT_SIGNING_KEY`, `RATE_LIMIT_KEY_SECRET` e tokens
de observabilidade. Não grave esses valores na imagem, no Compose ou no Git.

## Persistência

- PostgreSQL: dados relacionais e auditoria;
- `/var/lib/synergia/imports`: quarentena, originais aceitos e resultados;
- `/var/lib/synergia/avatars`: avatares privados;
- `/var/lib/synergia/email-capture`: somente quando o provedor local estiver
  em uso.

O ambiente corporativo deve definir retenção, criptografia, backup, restauração
e permissões desses volumes antes da homologação.

## Sondas e operação

- `GET /health/live`: processo da API vivo;
- `GET /health/ready`: banco, schema e armazenamento prontos;
- frontend `/`: conteúdo servido pelo Nginx.

Migrations executam como tarefa finita antes da API. Um checksum diferente para
uma migration aplicada interrompe a implantação. Rollback de aplicação deve
usar imagens anteriores; rollback de schema exige plano específico e backup.

`MIGRATION_BASELINE_EXISTING=true` existe somente para adotar, após backup e
conferência, um banco legado que já recebeu todas as migrations mas não possui
a tabela de histórico. Não habilite essa variável em bancos novos nem como
configuração permanente.

## Informações ainda necessárias da LG

- orquestrador, registry, convenção de tags e arquiteturas de CPU;
- imagens-base permitidas e política de vulnerabilidades;
- ingress, DNS, TLS, proxy e caminhos-base;
- mecanismo de secrets e rotação;
- PostgreSQL gerenciado ou em container;
- classes de storage, backup e retenção;
- limites de CPU, memória e disco;
- integração com SSO, SMTP e observabilidade;
- procedimento de homologação, promoção, rollback e aceite.

Nenhuma integração corporativa deve ser considerada pronta apenas porque a
aplicação executa em containers.
