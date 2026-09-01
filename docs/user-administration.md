# Administracao do ciclo de vida de usuarios

Esta entrega disponibiliza contratos administrativos sobre o modelo persistente
de identidade. Recuperacao de senha, diretorio corporativo e telas
administrativas permanecem fora do escopo.

## Contexto administrativo

Todas as rotas exigem access token Bearer associado a usuário e sessão ativos.
O backend carrega `access.admin` do PostgreSQL em cada requisição. O antigo
cabecalho `X-Actor-Id` não é credencial e não substitui o token.

Todas as rotas usam o prefixo `/admin/users`. Falhas seguem o envelope comum:

```json
{
  "error": {
    "code": "user_version_conflict",
    "message": "O usuario foi alterado por outra operacao",
    "details": {}
  }
}
```

Mensagens de conflito e inexistencia nao revelam o identificador de outro
usuario, o proprietario de um e-mail nem qualquer segredo.

## Contratos

| Metodo e rota | Finalidade |
| --- | --- |
| `POST /admin/users` | criar usuario com um ou mais e-mails |
| `GET /admin/users/{id}` | consultar usuario por UUID interno |
| `GET /admin/users` | listar e filtrar usuarios |
| `PATCH /admin/users/{id}` | atualizar nome e conjunto de e-mails |
| `POST /admin/users/{id}/deactivate` | desativar e revogar sessoes |
| `POST /admin/users/{id}/reactivate` | reativar usuario inativo |
| `POST /admin/users/{id}/block` | bloquear e revogar sessoes |
| `POST /admin/users/{id}/unblock` | desbloquear usuario bloqueado |
| `DELETE /admin/users/{id}` | rejeitar exclusao fisica explicitamente |

A listagem aceita `status`, `group`, `role`, `organization`, `name`, `email`,
`page` e `page_size`. O limite maximo e 100 itens. A ordenacao fixa
`created_at,id` fornece desempate deterministico entre registros criados no
mesmo instante.

Na criacao, somente `pending` e `active` sao aceitos. Estados `inactive` e
`blocked` exigem uma operacao explicita de ciclo de vida, com versao e motivo;
enviá-los em `POST /admin/users` retorna HTTP `422` antes de acessar o banco.

## Exemplos

Criacao:

```http
POST /admin/users HTTP/1.1
Content-Type: application/json
Authorization: Bearer {{accessToken}}

{
  "display_name": "Usuario de Homologacao",
  "status": "active",
  "emails": [
    {
      "email": "usuario@example.invalid",
      "is_primary": true,
      "is_verified": false
    }
  ],
  "reason": "provisionamento administrativo"
}
```

Atualizacao com concorrencia otimista:

```http
PATCH /admin/users/22222222-2222-2222-2222-222222222222 HTTP/1.1
Content-Type: application/json
Authorization: Bearer {{accessToken}}

{
  "version": 3,
  "display_name": "Nome Atualizado",
  "emails": [
    {"email": "novo@example.invalid", "is_primary": true}
  ],
  "reason": "correcao solicitada pelo responsavel"
}
```

Uma versao desatualizada retorna HTTP `409` e `user_version_conflict`. O cliente
deve consultar o recurso novamente antes de decidir se repete a alteracao.

## Ciclo de vida e integridade

- `deactivate`: aceita `pending`, `active` ou `blocked` e produz `inactive`;
- `reactivate`: aceita somente `inactive` e produz `active`;
- `block`: aceita `pending` ou `active` e produz `blocked`;
- `unblock`: aceita somente `blocked` e produz `active`;
- desativacao e bloqueio revogam sessoes ativas pela trigger do modelo;
- o ultimo administrador ativo nao pode ser desativado nem bloqueado;
- desativacoes e bloqueios adquirem um lock transacional dedicado antes de
  avaliar administradores ativos; operacoes concorrentes sao serializadas e a
  segunda reavalia o total, retornando `last_active_admin` quando necessario;
- e-mails sao normalizados por `lower(btrim(email))`;
- e-mails removidos sao desabilitados, nao apagados;
- reintroduzir um e-mail do mesmo usuario reativa o vinculo historico;
- senha, hash de senha, refresh token e hash de token nunca aparecem na API;
- exclusao fisica retorna `physical_deletion_forbidden`.

## Auditoria

Criacao, atualizacao e transicoes registram em `identity_access_events` o ator,
usuario afetado, data, motivo e campos alterados. Eventos automaticos do modelo,
como `user.updated` e `session.revoked`, continuam append-only. Os eventos
administrativos sao `user.admin_created`, `user.admin_updated`,
`user.admin_deactivate`, `user.admin_reactivate`, `user.admin_block` e
`user.admin_unblock`.

## Validacao

```bash
cd backend
ruff check app tests
pytest -q tests/test_users.py
pytest -q -m integration tests/test_user_persistence.py
```

Os testes usam apenas identificadores e e-mails sinteticos sob
`example.invalid`.
