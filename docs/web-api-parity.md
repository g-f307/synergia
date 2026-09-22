# Paridade entre contratos FastAPI e jornadas Angular

## Finalidade

Esta auditoria complementa o mapa de jornadas e impede que a existência de uma
rota Angular seja interpretada como cobertura integral do domínio. O registro
canônico e validável por máquina permanece em
[`web-route-map.json`](web-route-map.json): seus endpoints de rota e suas
`supporting_operations` cobrem, sem duplicidade, todas as operações publicadas
no OpenAPI.

Contratos `full` também informam arquivos Angular de evidência. O validador
confirma que cada arquivo existe, contém o método HTTP e referencia, em ordem,
os segmentos estáticos do endpoint. Assim, uma declaração completa não pode se
apoiar apenas em `consumer` ou `owner` nominal.

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
| autenticação e perfil | login, refresh, logout, perfil, avatar, notificações, densidade e escala tipográfica | completo na #108 |
| dashboard | indicadores e registros relacionados | completo |
| importação | upload, política, inspeção, validação e resumo; normalizado sem ação web | parcial por decisão |
| execuções | localização por ID, detalhe, artefatos e reprocessamento | parcial; catálogo planejado na #107 |
| consultas | busca, Workorder, lote, serial e consolidado | completo |
| pendências e decisão | fila, detalhe, submissão, atribuição, devolução, reenvio e decisão | completo |
| relatórios | catálogo, geração, histórico, cancelamento e exportação | parcial; nova versão explícita permanece pendente |
| notificações | central, contador, leitura, preferências e gestão versionada de templates | completo na #110; SMTP corporativo permanece fora do escopo |
| administração de acesso | usuários, grupos, papéis, associações e permissões efetivas | completo na #106 |
| auditoria | consulta protegida disponível na API | interface adiada |
| saúde e métricas | sondas e métricas protegidas para plataforma | técnico, sem interface Angular |

## Jornada administrativa

A issue #106 completou a administração de usuários, grupos e papéis com listas
paginadas, filtros, criação, detalhe, edição, ciclo de vida e concorrência
otimista. As cinco associações podem ser concedidas e revogadas com motivo, em
escopo global ou organizacional quando o contrato permitir, e a tela do usuário
mostra permissões efetivas e suas origens.

Durante o planejamento foi aprovada uma extensão mínima de leitura para evitar
varrer todo o histórico de associações e impedir entrada manual de UUIDs de
organização. `GET /admin/access/associations` passou a aceitar filtros de
entidade, organização e vínculo ativo, e `GET /admin/access/organizations`
publica o catálogo paginado de organizações ativas. Ambos continuam protegidos
por `access.admin`; a autorização e a validação de escopo permanecem no backend.

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
- leitura administrativa de sessões: adiada até permissão explícita; sessões próprias implementadas na #109;
- Modo TV: adiado;
- conectores corporativos e RPA: Etapa 6, ainda não autorizada.

Notificações já emitidas não são CRUD administrativo: são ocorrências
imutáveis geradas por eventos. A administração da #110 atua somente sobre
revisões e ativações futuras, com `access.admin`, histórico e auditoria.

## Decisão sobre preferências pessoais

A issue #108 aprovou como preferências pessoais persistentes a densidade
`comfortable|compact` e a escala tipográfica `small|normal|large`, além de
preservar nome, idioma, fuso, avatar e canais `email`/`in_app`. O backend valida
os valores e o shell aplica as preferências após login, refresh e atualização
do perfil; respostas antigas ou desconhecidas recebem fallback visual seguro.

Tamanho padrão de página, período padrão de consultas e atualização automática
foram adiados: exigem semântica por jornada, limites operacionais e critérios de
atualização antes de virarem controles. Tema permanece uma opção local do shell,
sem contrato de sincronização. Modo TV continua fora do escopo.

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
- uma rota completa ainda registra lacuna ou possui operação parcial destinada
  ao mesmo consumidor;
- uma operação completa não possui referência Angular existente e compatível
  com seu método e caminho;
- uma operação informa consumidor desconhecido;
- uma operação técnica não possui justificativa;
- uma operação ou capacidade adiada não possui destino;
- uma rota marcada como implementada não existe no Angular.
