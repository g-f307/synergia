# Administracao de controle de acesso

Esta entrega implementa a fundacao administrativa da issue #40. Grupos e papeis
possuem ciclo de vida logico e versao otimista; permissoes pertencem a um
catalogo versionado e reservado. A aplicacao nao oferece uma rota para criar
permissoes fora desse catalogo.

## Fronteira de confianca

Todas as rotas exigem access token Bearer, usuário e sessão ativos e a permissão
global `access.admin` carregada do PostgreSQL. Nomes de papel no token e o
cabecalho legado `X-Actor-Id` não autorizam operações.

## Contratos

As rotas sob `/admin/access` permitem:

- criar, consultar, listar, alterar, ativar e desativar grupos e papeis;
- consultar o catalogo de permissoes, opcionalmente por `catalog_version`;
- consultar o catalogo paginado de organizacoes ativas para escolher escopos;
- conceder ou revogar relacoes usuario-grupo, usuario-papel, papel-permissao,
  grupo-papel e usuario-permissao com `PUT` e `DELETE` idempotentes;
- paginar associacoes por `granted_at`, tipo e identificador, com filtros por
  entidade, organizacao e estado ativo;
- calcular permissoes efetivas, informando a origem `direct`, `role` ou `group`.

Concessoes de papel e permissao podem receber `organization_id`. Uma
organizacao inexistente ou inativa, assim como usuario, grupo, papel ou
permissao inativos, produz `409`. Repetir uma concessao ativa ou uma revogacao
ja concluida retorna sucesso com `idempotent: true`.

## Jornada Angular e decisão da issue #106

A administração web usa apenas contratos FastAPI protegidos por
`access.admin`. Para suportar detalhes de entidades e seleção confiável de
escopo, foi aprovada durante a #106 uma extensão mínima, somente de leitura:

- filtros `left_id`, `right_id`, `organization_id` e `active_only` em
  `GET /admin/access/associations`;
- `GET /admin/access/organizations`, paginado e limitado a organizações ativas.

Essa decisão evita carregar todo o histórico no navegador e evita confiar em um
UUID de organização digitado pelo usuário. Concessões e revogações continuam
validando recursos, escopo e permissão no PostgreSQL, independentemente das
opções apresentadas pelo Angular.

## Integridade e auditoria

Alteracoes exigem um motivo, registram ator, data, recurso e detalhes em
`identity_access_events`, e nunca apagam o historico das associacoes. Grupos e
papeis usam o campo `version`; uma escrita baseada em versao antiga retorna
`409 access_version_conflict`.

Antes de remover qualquer caminho que conceda administracao, a transacao toma
um advisory lock e recalcula os administradores efetivos. A operacao e revertida
com `409 last_active_admin` caso removesse o ultimo administrador ativo.

O catalogo inicial `1.0.0` materializa os cinco papeis e as permissoes da matriz
de acesso. Evolucoes devem publicar uma nova versao por migration, preservando
as concessoes e evidencias anteriores.

## Validacao local

```bash
cd backend
ruff check app tests
pytest -q tests/test_access_control_persistence.py
```

O segundo comando requer PostgreSQL 16 com todas as migrations aplicadas e
`DATABASE_URL` configurada. Exemplos HTTP estao em
`docs/http/access-control.http`.
