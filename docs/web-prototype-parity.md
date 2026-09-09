# Matriz de paridade funcional com o protótipo

Referência: branch `prototype-pages`, tag `prototype-v1.0`. Esta matriz mede
capacidade funcional. A identidade e a composição visual das telas existentes
foram alinhadas na #69 e são verificadas separadamente na
[matriz de fidelidade visual](visual-fidelity-matrix.md).

## Inventário do protótipo

| Página | Componentes | Filtros/estado | Ações observadas | Destino |
| --- | --- | --- | --- | --- |
| `index.html` | KPIs, fontes, alertas, progresso e prioridades | período, lote, situação e texto | executar, abrir pendência, relatório e exportar | dashboard #60; executar vira link para #58; relatórios são adiados |
| `consulta.html` | busca, resumo, etapas, quantidades, seriais e contexto | tipo inferido e identificador | pesquisar, limpar, abrir pendência e Workorder | consulta e detalhes #61 |
| `monitor.html` | KPIs, tabela, paginação, logs e modal de execução | ID, resultado, tipo, fonte e página | nova execução, detalhe e reprocessamento | detalhe #59; nova execução aponta para #58; lista adapta-se à API |
| `pendencias.html` | KPIs, fila, badges e paginação | texto, estado, impacto, área, fonte, categoria, organização, tipo de WO e ordem | limpar, abrir detalhe e Workorder | fila #62; organização limitada ao escopo efetivo |
| `detalhe-pendencia.html` | contexto, histórico, observações, execução e decisão | ID da pendência | reprocessar, atribuir, anotar, aprovar/rejeitar | contexto somente leitura #62; decisão, atribuição e anotação são adiadas |
| `relatorios.html` | catálogo, cards, histórico e paginação | organização, tipo, estado, execução, ordenação e página | atualizar, gerar, visualizar e exportar | implementado #78 com filtros do contrato real |
| `visualizar-relatorio.html` | resumo, abas de dados e histórico e paginação | ID, versão, aba e página | voltar, navegar para entidades, cancelar e exportar | implementado #78 sobre snapshots persistidos |
| `configuracoes.html` | seletores, toggles e parâmetros bloqueados | tema, densidade, fonte, TV, atualização, período e tamanho de página | salvar preferências e solicitar acesso | preferências suportadas em `/profile`; TV, solicitação e parâmetros adiados |

O menu observado contém Dashboard, Consulta, Monitor, Pendências, Relatórios e
Configurações. A navegação alvo substitui Relatórios por Nova importação durante
a Etapa 3 e renomeia Configurações para Perfil e preferências.

## Matriz tela × contrato × permissão

| Tela alvo | Protótipo | Contratos principais | Permissão/escopo | Estado |
| --- | --- | --- | --- | --- |
| `/login` | ausente | `POST /auth/login`, `POST /auth/refresh` | público | implementado |
| `/dashboard` | `index.html` | `GET /indicators` | `dashboard.read` / `org` | implementado #60; filtros reais de organização e período preservados na URL |
| `/imports/new` | ausente | `POST /imports` | `import.create` / `org` | implementado #58 |
| `/imports/:executionId` | ausente | consultas `/imports/{execution_id}/*` | `import.read`, `artifact.read` / `org` | implementado #58 |
| `/executions` e `/executions/:executionId` | `monitor.html` | consultas `/executions/{execution_id}/*` | `execution.read`, `artifact.read` / `org` | implementado #59; localização por ID enquanto não existe contrato de listagem global |
| `/search` | `consulta.html` | busca e detalhes de Workorders, lotes e seriais | `business.read` / `org` | implementado #61; validado E2E #63 |
| detalhes de WO/lote/serial | `consulta.html` | detalhes e consolidado | `business.read` / `org` | implementado #61; validado E2E #63 |
| `/pending-items` | `pendencias.html` | `GET /pending-items` | `pending.read` / `org` | implementado #62 |
| `/pending-items/:pendingId` | `detalhe-pendencia.html` | `GET /pending-items/{pending_id}` | `pending.read` / `org` | implementado #62 |
| `/profile` | `configuracoes.html` | `GET/PATCH /me` | `profile.own` / `own` | implementado; visual alinhado #69 |
| `/admin` | ausente | `/admin/users`, `/admin/access/*` | `access.admin` / global | implementado; visual alinhado #69 |
| `/reports` e detalhe | páginas de relatório | `/reports`, `/reports/policy` e versões/exportação | `report.read`, `report.generate`, `report.export`, `report.cancel` / `org` | implementado #78 |
| `/notifications` | ícone de notificação | `/notifications`, contador e leitura | `notification.read` + permissão do recurso / `org` | implementado #79; somente canal interno |

O inventário integral e validável de endpoints está em
[`web-route-map.json`](web-route-map.json).

## Componentes e padrões

| Elemento do protótipo | Tratamento de produção |
| --- | --- |
| shell lateral, cabeçalho e breadcrumbs | implementado na #56 e alinhado ao protótipo na #69 |
| cards, badges, tabelas, filtros, paginação, alertas e modais | componentes acessíveis compartilhados, alinhados na #69 |
| temas, tipografia e responsividade | tokens extraídos e validados na #69; evitar estilos por página |
| foco, skip link, labels e redução de movimento | preservar e testar nas #56/#57 |
| dados de `data.js` | remover; somente fixtures de teste podem conter valores fixos |
| `localStorage` de sessão | remover; access token permanece em memória |
| toasts de ações simuladas | remover ou substituir por resultado real da API |
| links e IDs de demonstração | substituir por rotas e parâmetros tipados |

## Paridade por capacidade

| Capacidade | Decisão | Issue | Aceite final |
| --- | --- | --- | --- |
| autenticação, perfil e administração | implementado/adaptado | #44, #56, #57 | validado #63 |
| dashboard e indicadores | implementado | #60 | validado #63 |
| upload manual seguro | implementado, embora ausente no protótipo | #58 | validado no fluxo real #63 |
| acompanhamento da importação | implementado | #58 | validado no fluxo real #63 |
| execução, histórico, divergências e evidências | adaptado | #59 | validado #63 |
| busca e detalhe operacional | adaptado | #61 | validado #63 |
| fila e contexto de pendências | adaptado | #62 | validado #63 |
| aprovação, rejeição, atribuição e decisão OQC | remover da etapa | Etapa 4 | decisão registrada |
| relatórios e exportação final | implementado com CSV/JSON gerados pelo backend | #77/#78 | catálogo, versão, estados e exportação segura cobertos |
| notificações externas | remover da etapa | Etapa 4 | decisão registrada |
| Modo TV | adiar | futura | decisão registrada |

## Critério de atualização

Cada issue #56–#62 deve alterar `Aceite final` somente para a própria
capacidade e anexar testes/capturas. A #63 confirma o fluxo integrado e não pode
marcar como atendido item apoiado apenas por mock ou pelo `data.js` do
protótipo.
