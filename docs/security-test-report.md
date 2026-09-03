# Relatório da matriz de segurança

Relatório determinístico da suíte da issue #43. `permitido` e `negado`
representam os casos positivos e negativos exigidos para cada papel.

- operações privadas cobertas: 63
- papéis iniciais: 5
- combinações papel x operação: 315
- rotas públicas explicitamente verificadas: 3

| Operação | Permissão | Escopo | Permitido | Negado |
| --- | --- | --- | --- | --- |
| `POST /auth/logout` | `session.revoke.own` | `own` | admin, gestor, analista, operador, consulta |  |
| `POST /auth/logout-all` | `session.revoke.own` | `own` | admin, gestor, analista, operador, consulta |  |
| `GET /me` | `profile.own` | `own` | admin, gestor, analista, operador, consulta |  |
| `PATCH /me` | `profile.own` | `own` | admin, gestor, analista, operador, consulta |  |
| `POST /me/avatar` | `profile.own` | `own` | admin, gestor, analista, operador, consulta |  |
| `DELETE /me/avatar` | `profile.own` | `own` | admin, gestor, analista, operador, consulta |  |
| `GET /me/avatar` | `profile.own` | `own` | admin, gestor, analista, operador, consulta |  |
| `POST /imports` | `import.create` | `org` | gestor, operador | admin, analista, consulta |
| `GET /imports/policy` | `import.create` | `org` | gestor, operador | admin, analista, consulta |
| `GET /imports/{execution_id}` | `import.read` | `org` | gestor, analista, operador | admin, consulta |
| `GET /imports/{execution_id}/inspections` | `import.read` | `org` | gestor, analista, operador | admin, consulta |
| `GET /imports/{execution_id}/validation-report` | `artifact.read` | `org` | gestor, analista, operador | admin, consulta |
| `GET /imports/{execution_id}/normalized-data` | `artifact.read` | `org` | gestor, analista, operador | admin, consulta |
| `GET /imports/{execution_id}/pipeline-summary` | `import.read` | `org` | gestor, analista, operador | admin, consulta |
| `GET /executions/{execution_id}` | `execution.read` | `org` | gestor, analista, operador, consulta | admin |
| `GET /workorders/{workorder_number}` | `business.read` | `org` | gestor, analista, operador, consulta | admin |
| `GET /lots/{lot_number}` | `business.read` | `org` | gestor, analista, operador, consulta | admin |
| `GET /serials/{serial_number}` | `business.read` | `org` | gestor, analista, operador, consulta | admin |
| `GET /pending-items` | `pending.read` | `org` | gestor, analista, operador, consulta | admin |
| `GET /pending-items/{pending_id}` | `pending.read` | `org` | gestor, analista, operador, consulta | admin |
| `GET /history` | `audit.read` | `org` | admin, gestor, analista | operador, consulta |
| `GET /workorders/{workorder_number}/consolidated-result` | `business.read` | `org` | gestor, analista, operador, consulta | admin |
| `POST /executions/{execution_id}/reprocess` | `execution.reprocess` | `org` | gestor | admin, analista, operador, consulta |
| `GET /indicators` | `dashboard.read` | `org` | gestor, analista, operador, consulta | admin |
| `GET /executions/{execution_id}/divergences` | `artifact.read` | `org` | gestor, analista, operador | admin, consulta |
| `GET /executions/{execution_id}/classifications` | `execution.read` | `org` | gestor, analista, operador, consulta | admin |
| `GET /executions/{execution_id}/pending-items` | `execution.read` | `org` | gestor, analista, operador, consulta | admin |
| `GET /executions/{execution_id}/evidences` | `artifact.read` | `org` | gestor, analista, operador | admin, consulta |
| `GET /executions/{execution_id}/evidences/{evidence_id}/download` | `artifact.export` | `org` | gestor, analista | admin, operador, consulta |
| `POST /admin/users` | `access.admin` | `global` | admin | gestor, analista, operador, consulta |
| `GET /admin/users` | `access.admin` | `global` | admin | gestor, analista, operador, consulta |
| `GET /admin/users/{user_id}` | `access.admin` | `global` | admin | gestor, analista, operador, consulta |
| `PATCH /admin/users/{user_id}` | `access.admin` | `global` | admin | gestor, analista, operador, consulta |
| `POST /admin/users/{user_id}/deactivate` | `access.admin` | `global` | admin | gestor, analista, operador, consulta |
| `POST /admin/users/{user_id}/reactivate` | `access.admin` | `global` | admin | gestor, analista, operador, consulta |
| `POST /admin/users/{user_id}/block` | `access.admin` | `global` | admin | gestor, analista, operador, consulta |
| `POST /admin/users/{user_id}/unblock` | `access.admin` | `global` | admin | gestor, analista, operador, consulta |
| `DELETE /admin/users/{user_id}` | `access.admin` | `global` | admin | gestor, analista, operador, consulta |
| `POST /admin/access/groups` | `access.admin` | `global` | admin | gestor, analista, operador, consulta |
| `GET /admin/access/groups` | `access.admin` | `global` | admin | gestor, analista, operador, consulta |
| `GET /admin/access/groups/{group_id}` | `access.admin` | `global` | admin | gestor, analista, operador, consulta |
| `PATCH /admin/access/groups/{group_id}` | `access.admin` | `global` | admin | gestor, analista, operador, consulta |
| `POST /admin/access/groups/{group_id}/deactivate` | `access.admin` | `global` | admin | gestor, analista, operador, consulta |
| `POST /admin/access/groups/{group_id}/activate` | `access.admin` | `global` | admin | gestor, analista, operador, consulta |
| `POST /admin/access/roles` | `access.admin` | `global` | admin | gestor, analista, operador, consulta |
| `GET /admin/access/roles` | `access.admin` | `global` | admin | gestor, analista, operador, consulta |
| `GET /admin/access/roles/{role_id}` | `access.admin` | `global` | admin | gestor, analista, operador, consulta |
| `PATCH /admin/access/roles/{role_id}` | `access.admin` | `global` | admin | gestor, analista, operador, consulta |
| `POST /admin/access/roles/{role_id}/deactivate` | `access.admin` | `global` | admin | gestor, analista, operador, consulta |
| `POST /admin/access/roles/{role_id}/activate` | `access.admin` | `global` | admin | gestor, analista, operador, consulta |
| `GET /admin/access/permissions` | `access.admin` | `global` | admin | gestor, analista, operador, consulta |
| `PUT /admin/access/users/{left_id}/groups/{right_id}` | `access.admin` | `global` | admin | gestor, analista, operador, consulta |
| `DELETE /admin/access/users/{left_id}/groups/{right_id}` | `access.admin` | `global` | admin | gestor, analista, operador, consulta |
| `PUT /admin/access/users/{left_id}/roles/{right_id}` | `access.admin` | `global/org` | admin | gestor, analista, operador, consulta |
| `DELETE /admin/access/users/{left_id}/roles/{right_id}` | `access.admin` | `global/org` | admin | gestor, analista, operador, consulta |
| `PUT /admin/access/roles/{left_id}/permissions/{right_id}` | `access.admin` | `global` | admin | gestor, analista, operador, consulta |
| `DELETE /admin/access/roles/{left_id}/permissions/{right_id}` | `access.admin` | `global` | admin | gestor, analista, operador, consulta |
| `PUT /admin/access/groups/{left_id}/roles/{right_id}` | `access.admin` | `global/org` | admin | gestor, analista, operador, consulta |
| `DELETE /admin/access/groups/{left_id}/roles/{right_id}` | `access.admin` | `global/org` | admin | gestor, analista, operador, consulta |
| `PUT /admin/access/users/{left_id}/permissions/{right_id}` | `access.admin` | `global/org` | admin | gestor, analista, operador, consulta |
| `DELETE /admin/access/users/{left_id}/permissions/{right_id}` | `access.admin` | `global/org` | admin | gestor, analista, operador, consulta |
| `GET /admin/access/associations` | `access.admin` | `global` | admin | gestor, analista, operador, consulta |
| `GET /admin/access/users/{user_id}/effective-permissions` | `access.admin` | `global/org` | admin | gestor, analista, operador, consulta |

## Evidências automatizadas

- `test_security_matrix_persistence.py`: 315 requisições HTTP reais
  com JWT, papéis e permissões carregados do PostgreSQL;
- `test_security_regression.py`: completude OpenAPI, mass assignment,
  respostas uniformes e ausência de segredos;
- `test_auth.py`: tokens expirados, adulterados, emissor, audiência
  e algoritmo inválidos;
- `test_auth_persistence.py`: replay sequencial e concorrente,
  revogação, usuário bloqueado e auditoria de autenticação;
- `test_authorization_persistence.py`: escopo horizontal e vertical,
  mudança de papel, sessão revogada e auditoria de negações;
- PostgreSQL 16: todos os testes `integration` no job `project-data`.

A suíte usa somente UUIDs, domínios `.invalid` e dados sintéticos.
