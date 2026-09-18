# Paridade entre contratos FastAPI e jornadas Angular

## Finalidade

Esta auditoria complementa o mapa de jornadas e impede que a existência de uma
rota Angular seja interpretada como cobertura integral do domínio. O registro
canônico e validável por máquina permanece em
[`web-route-map.json`](web-route-map.json): seus endpoints de rota e suas
`supporting_operations` cobrem, sem duplicidade, todas as operações publicadas
no OpenAPI.

Cada contrato recebe uma das decisões abaixo:

| Decisão | Significado |
| --- | --- |
| `full` | a ação necessária está disponível na jornada Angular ou no shell autenticado |
| `partial` | existe consumo ou tela parcial, mas faltam ações relevantes já contratadas |
| `technical` | superfície destinada à plataforma ou contrato defensivo sem interface de usuário |
| `planned` | capacidade aprovada, ainda sem contrato OpenAPI completo |
| `deferred` | capacidade adiada com justificativa e destino explícitos |

## Resultado da auditoria

| Domínio | Situação web | Decisão |
| --- | --- | --- |
| autenticação e perfil | login, refresh, logout, perfil, avatar e preferências suportadas | completo |
| dashboard | indicadores e registros relacionados | completo |
| importação | upload, política, inspeção, validação e resumo; normalizado sem ação web | parcial por decisão |
| execuções | localização por ID, detalhe, artefatos e reprocessamento | parcial; catálogo planejado na #107 |
| consultas | busca, Workorder, lote, serial e consolidado | completo |
| pendências e decisão | fila, detalhe, submissão, atribuição, devolução, reenvio e decisão | completo |
| relatórios | catálogo, geração, histórico, cancelamento e exportação | parcial; nova versão explícita permanece pendente |
| notificações | central, contador, leitura e preferências | completo para ocorrências; templates na #110 |
| administração de acesso | listas resumidas de usuários, grupos e papéis | parcial; gestão completa na #106 |
| auditoria | consulta protegida disponível na API | interface adiada |
| saúde e métricas | sondas e métricas protegidas para plataforma | técnico, sem interface Angular |

## Lacuna administrativa

A rota `/admin` não representa CRUD completo. A implementação atual executa
somente `GET /admin/users`, `GET /admin/access/groups` e
`GET /admin/access/roles`. O catálogo de permissões está relacionado à rota,
mas as ações de criação, detalhe, edição, ciclo de vida, concessão, revogação e
permissões efetivas não são expostas pelo Angular.

Por isso, `/admin` permanece uma rota implementada com `exposure=partial`. A
#106 é responsável por completar a jornada. A classificação só poderá mudar
para `full` quando os contratos administrativos estiverem cobertos por testes
Angular e E2E reais.

## Contratos deliberadamente sem tela

- `/health`, `/health/live` e `/health/ready` pertencem ao orquestrador;
- `/metrics` pertence ao coletor e usa credencial técnica própria;
- `DELETE /admin/users/{user_id}` existe para rejeitar exclusão física com
  `409`, não para oferecer um botão de exclusão;
- dados normalizados permanecem protegidos na API até existir uma regra de
  exposição aprovada;
- o histórico auditável permanece consultável pela API enquanto uma jornada
  própria não define filtros, retenção e público autorizado.

## Capacidades sem contrato completo

- catálogo paginado de execuções: #107;
- preferências pessoais adicionais suportadas: #108;
- consulta e revogação individual de sessões: #109;
- gestão versionada de templates de notificação: #110;
- Modo TV: adiado;
- conectores corporativos e RPA: Etapa 6, ainda não autorizada.

Notificações já emitidas não são CRUD administrativo: são ocorrências
imutáveis geradas por eventos. A futura administração atua sobre templates e
políticas versionados.

## Verificação automática

Execute:

```bash
python scripts/validate_web_journey_map.py
pytest -q backend/tests/test_web_journey_map.py
```

O validador reprova quando:

- uma operação OpenAPI não possui decisão;
- uma operação aparece mais de uma vez;
- permissão ou escopo divergem da matriz de acesso;
- uma rota parcial não registra sua lacuna;
- uma operação técnica não possui justificativa;
- uma operação ou capacidade adiada não possui destino;
- uma rota marcada como implementada não existe no Angular.
