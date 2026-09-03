# Matriz inicial de acesso

Esta matriz especifica a política-alvo da Etapa 2. O catálogo, os papéis, as
associações e a consulta de permissões efetivas estão implementados pela camada
administrativa descrita em
[administração de acesso](access-control-administration.md). Login, tokens e
sessões estão implementados conforme [autenticação](authentication.md). A matriz
é aplicada no backend conforme [autorização](authorization.md); telas continuam
incrementais e não concedem acesso.

A estratégia de identidade, sessão e troca de provedor está em
[ADR 0001](adr/0001-identity-strategy.md). O backend deverá autorizar a ação,
o recurso e o escopo em cada requisição. Ocultar um menu não concede nem
revoga acesso.

## Convenções

- `✓`: papel recebe a permissão por padrão;
- `—`: papel não recebe a permissão; negar é o comportamento padrão;
- uma pessoa pode acumular papéis apenas quando a regra de segregação permitir;
- `own`: somente a própria sessão; `org`: uma das organizações do ator; `all`:
  todas as organizações, quando concedido explicitamente;
- consultas por identificador retornam `404` tanto para recurso inexistente
  quanto fora do escopo, evitando enumeração horizontal;
- filtros enviados pelo cliente só estreitam o escopo: nunca o ampliam.

## Papéis e catálogo de permissões

Papéis são conjuntos convenientes; permissões são o contrato de autorização.
Não há herança implícita nem papel `superuser`.

| Ação | Recurso | admin | gestor | analista | operador | consulta |
| --- | --- | :---: | :---: | :---: | :---: | :---: |
| `dashboard.read` | indicadores | — | ✓ | ✓ | ✓ | ✓ |
| `execution.read` | execução, classificação e pendência | — | ✓ | ✓ | ✓ | ✓ |
| `business.read` | Workorder, lote, serial e consolidado | — | ✓ | ✓ | ✓ | ✓ |
| `pending.read` | fila e detalhe de pendências | — | ✓ | ✓ | ✓ | ✓ |
| `import.create` | arquivo de entrada | — | ✓ | — | ✓ | — |
| `import.read` | estado, inspeção e resumo do pipeline | — | ✓ | ✓ | ✓ | — |
| `artifact.read` | validação, normalizado, divergência e evidência | — | ✓ | ✓ | ✓ | — |
| `execution.reprocess` | execução | — | ✓ | — | — | — |
| `audit.read` | histórico auditável | ✓ | ✓ | ✓ | — | — |
| `artifact.export` | download de evidência aceita | — | ✓ | ✓ | — | — |
| `report.export` | relatório/sumário futuro | — | ✓ | ✓ | — | — |
| `access.admin` | usuário, vínculo, papel e escopo futuros | ✓ | — | — | — | — |
| `session.revoke.any` | sessão de outro usuário futura | ✓ | — | — | — | — |
| `session.revoke.own` | própria sessão futura | ✓ | ✓ | ✓ | ✓ | ✓ |

`report.export`, `access.admin` e as ações de sessão reservam a política dos
endpoints planejados; não afirmam que eles já existem. Um novo endpoint privado
deve reutilizar ou acrescentar uma ação e entrar no inventário antes do merge.

### Capacidades por papel

- `admin`: administra identidades, vínculos, papéis, escopos e revogações. Não
  recebe operações de negócio por ser administrador.
- `gestor`: supervisiona a operação, pode importar contingência, reprocessar e
  exportar. Não administra os próprios acessos.
- `analista`: investiga dados, artefatos e auditoria e produz exportações, sem
  iniciar importação ou reprocessamento.
- `operador`: executa importação controlada e investiga o processamento, sem
  reprocessar, exportar ou administrar.
- `consulta`: vê indicadores e resultados operacionais já consolidados.

## Inventário das rotas privadas atuais

Todas as operações OpenAPI atuais, exceto `GET /health`, `/docs`, `/redoc` e
`/openapi.json`, serão privadas. As três últimas são rotas técnicas do FastAPI
e não aparecem em `paths` do OpenAPI. Em produção, a publicação da documentação
técnica também dependerá da política de rede da TI.

| Método e rota | Ação | Recurso | Escopo | Papéis autorizados |
| --- | --- | --- | --- | --- |
| `POST /auth/logout` | `session.revoke.own` | sessão atual | `own` | admin, gestor, analista, operador, consulta |
| `POST /auth/logout-all` | `session.revoke.own` | sessões próprias | `own` | admin, gestor, analista, operador, consulta |
| `GET /me` | `profile.own` | perfil próprio | `own` | admin, gestor, analista, operador, consulta |
| `PATCH /me` | `profile.own` | perfil próprio | `own` | admin, gestor, analista, operador, consulta |
| `POST /me/avatar` | `profile.own` | avatar próprio | `own` | admin, gestor, analista, operador, consulta |
| `DELETE /me/avatar` | `profile.own` | avatar próprio | `own` | admin, gestor, analista, operador, consulta |
| `GET /me/avatar` | `profile.own` | avatar próprio | `own` | admin, gestor, analista, operador, consulta |
| `POST /imports` | `import.create` | importação | `org` | gestor, operador |
| `GET /imports/policy` | `import.create` | política ativa de upload | `org` | gestor, operador |
| `GET /imports/{execution_id}` | `import.read` | importação | `org` | gestor, analista, operador |
| `GET /imports/{execution_id}/inspections` | `import.read` | inspeções | `org` | gestor, analista, operador |
| `GET /imports/{execution_id}/validation-report` | `artifact.read` | validação | `org` | gestor, analista, operador |
| `GET /imports/{execution_id}/normalized-data` | `artifact.read` | dados normalizados | `org` | gestor, analista, operador |
| `GET /imports/{execution_id}/pipeline-summary` | `import.read` | resumo do pipeline | `org` | gestor, analista, operador |
| `GET /executions/{execution_id}` | `execution.read` | execução | `org` | gestor, analista, operador, consulta |
| `GET /workorders/{workorder_number}` | `business.read` | Workorder | `org` | gestor, analista, operador, consulta |
| `GET /lots/{lot_number}` | `business.read` | lote | `org` | gestor, analista, operador, consulta |
| `GET /serials/{serial_number}` | `business.read` | serial | `org` | gestor, analista, operador, consulta |
| `GET /pending-items` | `pending.read` | pendências | `org` | gestor, analista, operador, consulta |
| `GET /pending-items/{pending_id}` | `pending.read` | pendência | `org` | gestor, analista, operador, consulta |
| `GET /history` | `audit.read` | eventos | `org` | admin, gestor, analista |
| `GET /workorders/{workorder_number}/consolidated-result` | `business.read` | consolidado | `org` | gestor, analista, operador, consulta |
| `POST /executions/{execution_id}/reprocess` | `execution.reprocess` | execução | `org` | gestor |
| `GET /indicators` | `dashboard.read` | indicadores | `org` | gestor, analista, operador, consulta |
| `GET /indicators/{entity}` | `dashboard.read` | registros relacionados aos indicadores | `org` | gestor, analista, operador, consulta |
| `GET /executions/{execution_id}/divergences` | `artifact.read` | divergências | `org` | gestor, analista, operador |
| `GET /executions/{execution_id}/classifications` | `execution.read` | classificações | `org` | gestor, analista, operador, consulta |
| `GET /executions/{execution_id}/pending-items` | `execution.read` | pendências da execução | `org` | gestor, analista, operador, consulta |
| `GET /executions/{execution_id}/evidences` | `artifact.read` | metadados de evidência | `org` | gestor, analista, operador |
| `GET /executions/{execution_id}/evidences/{evidence_id}/download` | `artifact.export` | arquivo de evidência | `org` | gestor, analista |
| `POST /admin/users` | `access.admin` | usuário | global | admin |
| `GET /admin/users` | `access.admin` | usuários | global | admin |
| `GET /admin/users/{user_id}` | `access.admin` | usuário | global | admin |
| `PATCH /admin/users/{user_id}` | `access.admin` | usuário | global | admin |
| `POST /admin/users/{user_id}/deactivate` | `access.admin` | usuário | global | admin |
| `POST /admin/users/{user_id}/reactivate` | `access.admin` | usuário | global | admin |
| `POST /admin/users/{user_id}/block` | `access.admin` | usuário | global | admin |
| `POST /admin/users/{user_id}/unblock` | `access.admin` | usuário | global | admin |
| `DELETE /admin/users/{user_id}` | `access.admin` | usuário | global | admin |
| `POST /admin/access/groups` | `access.admin` | grupo | global | admin |
| `GET /admin/access/groups` | `access.admin` | grupos | global | admin |
| `GET /admin/access/groups/{group_id}` | `access.admin` | grupo | global | admin |
| `PATCH /admin/access/groups/{group_id}` | `access.admin` | grupo | global | admin |
| `POST /admin/access/groups/{group_id}/deactivate` | `access.admin` | grupo | global | admin |
| `POST /admin/access/groups/{group_id}/activate` | `access.admin` | grupo | global | admin |
| `POST /admin/access/roles` | `access.admin` | papel | global | admin |
| `GET /admin/access/roles` | `access.admin` | papéis | global | admin |
| `GET /admin/access/roles/{role_id}` | `access.admin` | papel | global | admin |
| `PATCH /admin/access/roles/{role_id}` | `access.admin` | papel | global | admin |
| `POST /admin/access/roles/{role_id}/deactivate` | `access.admin` | papel | global | admin |
| `POST /admin/access/roles/{role_id}/activate` | `access.admin` | papel | global | admin |
| `GET /admin/access/permissions` | `access.admin` | catálogo de permissões | global | admin |
| `PUT /admin/access/users/{left_id}/groups/{right_id}` | `access.admin` | vínculo usuário-grupo | global | admin |
| `DELETE /admin/access/users/{left_id}/groups/{right_id}` | `access.admin` | vínculo usuário-grupo | global | admin |
| `PUT /admin/access/users/{left_id}/roles/{right_id}` | `access.admin` | vínculo usuário-papel | global/org | admin |
| `DELETE /admin/access/users/{left_id}/roles/{right_id}` | `access.admin` | vínculo usuário-papel | global/org | admin |
| `PUT /admin/access/roles/{left_id}/permissions/{right_id}` | `access.admin` | vínculo papel-permissão | global | admin |
| `DELETE /admin/access/roles/{left_id}/permissions/{right_id}` | `access.admin` | vínculo papel-permissão | global | admin |
| `PUT /admin/access/groups/{left_id}/roles/{right_id}` | `access.admin` | vínculo grupo-papel | global/org | admin |
| `DELETE /admin/access/groups/{left_id}/roles/{right_id}` | `access.admin` | vínculo grupo-papel | global/org | admin |
| `PUT /admin/access/users/{left_id}/permissions/{right_id}` | `access.admin` | concessão direta | global/org | admin |
| `DELETE /admin/access/users/{left_id}/permissions/{right_id}` | `access.admin` | concessão direta | global/org | admin |
| `GET /admin/access/associations` | `access.admin` | associações de acesso | global | admin |
| `GET /admin/access/users/{user_id}/effective-permissions` | `access.admin` | permissões efetivas | global/org | admin |

`GET /health`, `POST /auth/login` e `POST /auth/refresh` permanecem públicos e
não retornam dados operacionais sem validar sua própria credencial. Upload é
restrito a `import.create`; reprocessamento a `execution.reprocess`; downloads e
futuras exportações às ações `artifact.export` e `report.export`;
administração a `access.admin`.

## Escopo por organização

O escopo organizacional é **obrigatório** para dados operacionais. Cada vínculo
de papel terá `organization_scope = list` com um ou mais `organization_id`, ou
`all` quando aprovado. `all` não decorre do papel `admin`; é uma concessão
separada e auditável.

Na implementação vigente:

1. importação exigirá exatamente uma organização autorizada, registrada na
   execução e propagada aos artefatos;
2. listas aplicarão o conjunto de organizações no repositório antes de paginação
   e agregação;
3. detalhes validarão a organização do recurso no servidor;
4. Workorder, lote ou serial presente em várias organizações exigirá contexto
   inequívoco; não será escolhido pelo registro mais recente fora do escopo;
5. indicadores e exportações serão calculados somente sobre o escopo efetivo;
6. uma troca de organização na interface não altera as concessões do token.

A migration `0017` vincula cada nova execução ao UUID IAM e as entidades
derivadas herdam esse escopo pela execução. O portão `ID-P06` ainda deve
fornecer o catálogo e os responsáveis de produção.

## Segregação de função

- quem concede `access.admin`, papéis ou `organization_scope` não pode aprovar
  a própria concessão;
- `admin` não recebe automaticamente importação, reprocessamento ou exportação;
- a combinação `admin` + `gestor` é proibida em produção; exceção temporária
  exige aprovador distinto, prazo, justificativa e evento auditável;
- `operador` não reprocessa nem exporta; `analista` não importa nem reprocessa;
- reprocessamento exige justificativa/origem técnica e preserva a execução
  anterior; o ator e a sessão são auditados;
- exportação exige organização autorizada, registra ator, sessão, filtros e
  recurso, e nunca amplia o conjunto consultável;
- conta de serviço não recebe papel humano nem acesso interativo. Suas
  permissões são específicas ao conector e fora desta matriz humana;
- decisão OQC, liberação, planejamento e correção de sistemas de origem
  continuam fora do SYNERGIA, conforme o levantamento.

O backend deve rejeitar na atribuição combinações incompatíveis, e não apenas
na interface administrativa.

## Verificações da matriz

| Verificação obrigatória | Evidência nesta entrega | Resultado |
| --- | --- | --- |
| Completude contra OpenAPI | `python scripts/validate_access_matrix.py` compara todas as operações atuais | aprovado quando o comando termina com `OK` |
| Toda ação privada aparece | inventário acompanha automaticamente as operações privadas; saúde é a única exceção pública | coberto |
| Conflitos entre papéis | revisão cruzada das colunas e regras acima | sem papel com administração e operação por padrão; combinações críticas explicitamente proibidas |
| Acesso horizontal | regra `org` em cada rota e comportamento de listas/detalhes | implementado e coberto em PostgreSQL |
| Acesso vertical | permissão por ação, negação padrão e papéis não hierárquicos | implementado e coberto em PostgreSQL |

## Pendências para implementação

Além dos portões `ID-P01` a `ID-P07` da ADR:

| ID | Pendência | Responsável |
| --- | --- | --- |
| AUTH-P01 | confirmar se operador pode importar para qualquer organização concedida ou apenas para uma organização primária | Gestor |
| AUTH-P02 | definir dupla aprovação e retenção para concessões administrativas | TI/Gestor |
| AUTH-P03 | classificar campos sensíveis de normalizados, evidências e exportações | Segurança/DPO/Gestor |
| AUTH-P04 | decidir formato e limite dos relatórios exportáveis | Gestor |
| AUTH-P05 | revisar esta matriz por integrante diferente do autor antes do merge | Revisor do PR |
