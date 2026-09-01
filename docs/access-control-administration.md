# Administracao de controle de acesso

Esta entrega implementa a fundacao administrativa da issue #40. Grupos e papeis
possuem ciclo de vida logico e versao otimista; permissoes pertencem a um
catalogo versionado e reservado. A aplicacao nao oferece uma rota para criar
permissoes fora desse catalogo.

## Fronteira de confianca

Todas as rotas usam a mesma fronteira temporaria de identidade descrita em
`user-administration.md`: o cabecalho `X-Actor-Id` so pode ser habilitado em
desenvolvimento, teste ou homologacao. Producao recusa essa configuracao. O ator
tambem precisa estar ativo e possuir o papel `admin` ou a permissao
`access.admin` no PostgreSQL.

## Contratos

As rotas sob `/admin/access` permitem:

- criar, consultar, listar, alterar, ativar e desativar grupos e papeis;
- consultar o catalogo de permissoes, opcionalmente por `catalog_version`;
- conceder ou revogar relacoes usuario-grupo, usuario-papel, papel-permissao,
  grupo-papel e usuario-permissao com `PUT` e `DELETE` idempotentes;
- paginar todas as associacoes por `granted_at`, tipo e identificador;
- calcular permissoes efetivas, informando a origem `direct`, `role` ou `group`.

Concessoes de papel e permissao podem receber `organization_id`. Uma
organizacao inexistente ou inativa, assim como usuario, grupo, papel ou
permissao inativos, produz `409`. Repetir uma concessao ativa ou uma revogacao
ja concluida retorna sucesso com `idempotent: true`.

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
