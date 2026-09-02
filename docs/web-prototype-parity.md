# Matriz de paridade funcional com o protótipo

Referência: branch `prototype-pages`, tag `prototype-v1.0`. Esta matriz mede
capacidade funcional, não identidade pixel a pixel. O aceite final será
atualizado pela #63.

## Inventário do protótipo

| Página | Componentes | Filtros/estado | Ações observadas | Destino |
| --- | --- | --- | --- | --- |
| `index.html` | KPIs, fontes, alertas, progresso e prioridades | período, lote, situação e texto | executar, abrir pendência, relatório e exportar | dashboard #60; executar vira link para #58; relatórios são adiados |
| `consulta.html` | busca, resumo, etapas, quantidades, seriais e contexto | tipo inferido e identificador | pesquisar, limpar, abrir pendência e Workorder | consulta e detalhes #61 |
| `monitor.html` | KPIs, tabela, paginação, logs e modal de execução | ID, resultado, tipo, fonte e página | nova execução, detalhe e reprocessamento | detalhe #59; nova execução aponta para #58; lista adapta-se à API |
| `pendencias.html` | KPIs, fila, badges e paginação | texto, estado, impacto, área, fonte, categoria, organização, tipo de WO e ordem | limpar, abrir detalhe e Workorder | fila #62; organização limitada ao escopo efetivo |
| `detalhe-pendencia.html` | contexto, histórico, observações, execução e decisão | ID da pendência | reprocessar, atribuir, anotar, aprovar/rejeitar | contexto somente leitura #62; decisão, atribuição e anotação são adiadas |
| `relatorios.html` | catálogo, cards, histórico e paginação | período, tipo, situação e texto | atualizar, visualizar e exportar | adiado para Etapa 4 |
| `visualizar-relatorio.html` | resumo, abas de Workorders/OQC/pendências e paginação | ID, aba e página | voltar, navegar para entidades e exportar | consultas distribuídas entre #59–#62; relatório adiado |
| `configuracoes.html` | seletores, toggles e parâmetros bloqueados | tema, densidade, fonte, TV, atualização, período e tamanho de página | salvar preferências e solicitar acesso | preferências suportadas em `/profile`; TV, solicitação e parâmetros adiados |

O menu observado contém Dashboard, Consulta, Monitor, Pendências, Relatórios e
Configurações. A navegação alvo substitui Relatórios por Nova importação durante
a Etapa 3 e renomeia Configurações para Perfil e preferências.

## Matriz tela × contrato × permissão

| Tela alvo | Protótipo | Contratos principais | Permissão/escopo | Estado |
| --- | --- | --- | --- | --- |
| `/login` | ausente | `POST /auth/login`, `POST /auth/refresh` | público | implementado |
| `/dashboard` | `index.html` | `GET /indicators` | `dashboard.read` / `org` | implementar #60 |
| `/imports/new` | ausente | `POST /imports` | `import.create` / `org` | implementar #58 |
| `/imports/:executionId` | ausente | consultas `/imports/{execution_id}/*` | `import.read`, `artifact.read` / `org` | implementar #58 |
| `/executions/:executionId` | `monitor.html` | consultas `/executions/{execution_id}/*` | `execution.read`, `artifact.read` / `org` | implementar #59 |
| `/search` | `consulta.html` | `GET /workorders`, `/lots`, `/serials` por ID | `business.read` / `org` | implementar #61 |
| detalhes de WO/lote/serial | `consulta.html` | detalhes e consolidado | `business.read` / `org` | implementar #61 |
| `/pending-items` | `pendencias.html` | `GET /pending-items` | `pending.read` / `org` | implementar #62 |
| `/pending-items/:pendingId` | `detalhe-pendencia.html` | `GET /pending-items/{pending_id}` | `pending.read` / `org` | implementar #62 |
| `/profile` | `configuracoes.html` | `GET/PATCH /me` | `profile.own` / `own` | adaptar #56/#57 |
| `/admin` | ausente | `/admin/users`, `/admin/access/*` | `access.admin` / global | adaptar #56/#57 |
| `/reports` e detalhe | páginas de relatório | nenhum contrato atual | `report.export` reservado / `org` | adiar Etapa 4 |

O inventário integral e validável de endpoints está em
[`web-route-map.json`](web-route-map.json).

## Componentes e padrões

| Elemento do protótipo | Tratamento de produção |
| --- | --- |
| shell lateral, cabeçalho e breadcrumbs | implementar na #56 com navegação por permissão |
| cards, badges, tabelas, filtros, paginação, alertas e modais | adaptar como componentes acessíveis da #56 |
| temas, tipografia e responsividade | adaptar tokens; evitar estilos por página |
| foco, skip link, labels e redução de movimento | preservar e testar nas #56/#57 |
| dados de `data.js` | remover; somente fixtures de teste podem conter valores fixos |
| `localStorage` de sessão | remover; access token permanece em memória |
| toasts de ações simuladas | remover ou substituir por resultado real da API |
| links e IDs de demonstração | substituir por rotas e parâmetros tipados |

## Paridade por capacidade

| Capacidade | Decisão | Issue | Aceite final |
| --- | --- | --- | --- |
| autenticação, perfil e administração | implementar/adaptar | #44, #56, #57 | pendente #63 |
| dashboard e indicadores | implementar | #60 | pendente #63 |
| upload manual seguro | implementar, embora ausente no protótipo | #58 | pendente #63 |
| acompanhamento da importação | implementar | #58 | pendente #63 |
| execução, histórico, divergências e evidências | adaptar | #59 | pendente #63 |
| busca e detalhe operacional | adaptar | #61 | pendente #63 |
| fila e contexto de pendências | adaptar | #62 | pendente #63 |
| aprovação, rejeição, atribuição e decisão OQC | remover da etapa | Etapa 4 | decisão registrada |
| relatórios e exportação final | adiar | Etapa 4 | decisão registrada |
| notificações externas | remover da etapa | Etapa 4 | decisão registrada |
| Modo TV | adiar | futura | decisão registrada |

## Critério de atualização

Cada issue #56–#62 deve alterar `Aceite final` somente para a própria
capacidade e anexar testes/capturas. A #63 confirma o fluxo integrado e não pode
marcar como atendido item apoiado apenas por mock ou pelo `data.js` do
protótipo.
