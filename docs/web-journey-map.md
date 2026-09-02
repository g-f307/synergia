# Mapa de jornadas da aplicação web

Este documento transforma o protótipo `prototype-v1.0`, os contratos OpenAPI e
a matriz de acesso em um plano implementável para a Etapa 3. O registro
canônico e validável das rotas está em
[`web-route-map.json`](web-route-map.json). O protótipo permanece congelado e
não será copiado para a aplicação.

## Princípios

- A aplicação consulta somente APIs; planilhas e banco nunca completam uma tela.
- O backend continua sendo a autoridade de autorização e de escopo.
- Identificadores permanecem texto e preservam zeros à esquerda.
- Estado ausente não vira zero e resultado parcial não parece completo.
- Simulações do protótipo só viram ações quando existe contrato real.
- Filtros que alteram o conjunto, a ordem ou a posição ficam na URL.
- Detalhes fora do escopo usam a política `404`; `403` representa ação conhecida
  sem permissão e não indisponibilidade.

## Navegação alvo

| Grupo | Entrada | Rota | Permissão | Issue |
| --- | --- | --- | --- | --- |
| Visão geral | Dashboard | `/dashboard` | `dashboard.read` | #60 |
| Operação | Nova importação | `/imports/new` | `import.create` | #58 |
| Operação | Execuções | `/executions/:executionId` | `execution.read` | #59 |
| Operação | Consulta operacional | `/search` | `business.read` | #61 |
| Operação | Pendências | `/pending-items` | `pending.read` | #62 |
| Conta | Perfil e preferências | `/profile` | `profile.own` | #44 |
| Sistema | Administração | `/admin` | `access.admin` | #44 |

Relatórios não aparecem no menu da Etapa 3. Login é público, e rotas de detalhe
aparecem por navegação contextual. O shell da #56 deve montar o menu com as
permissões efetivas retornadas por `/me`, sem substituir a recusa do servidor.

## Jornadas

### Autenticação e retorno

1. A rota protegida envia o usuário anônimo para `/login?returnUrl=...`.
2. O login cria a sessão e retorna apenas para uma rota interna validada.
3. O shell carrega `/me`, aplica idioma e permissões e abre o destino.
4. `401` tenta renovação uma única vez; falha limpa a sessão. `403` mantém a
   sessão e apresenta acesso proibido.

### Importação até execução

1. `/imports/new` apresenta fonte, formatos e limites antes da seleção.
2. `POST /imports` realiza a inspeção real e devolve a execução.
3. Rejeição ou quarentena permanece na jornada de importação; aceite direciona
   para `/imports/:executionId` e depois `/executions/:executionId`.
4. O detalhe da execução separa resumo, histórico, divergências,
   classificações, pendências e evidências por `tab` na URL.

### Consulta operacional

1. `/search?type=workorder|lot|serial&query=...` preserva o identificador como
   texto e chama o contrato correspondente.
2. O resultado navega para `/workorders/:id`, `/lots/:id` ou `/serials/:id`.
3. `from` preserva o retorno à busca; links para execução e pendência mantêm o
   contexto organizacional já autorizado.
4. A API atual oferece consulta direta, não uma busca paginada geral. A #61 deve
   adaptar a primeira entrega a resultados exatos ou acrescentar um contrato
   aprovado antes de prometer múltiplos resultados.

### Pendências

1. `/pending-items` inicia com itens ativos e filtros reproduzíveis na URL.
2. `/pending-items/:pendingId` explica regra, versão, prioridade, motivo,
   proveniência e relações.
3. A tela pode navegar para Workorder e execução, mas não aprova, rejeita nem
   encerra a pendência nesta etapa.

## Breadcrumbs e retorno

| Rota | Breadcrumb | Retorno |
| --- | --- | --- |
| `/imports/:executionId` | Nova importação › Importação `{id}` | `/imports/new` |
| `/executions/:executionId` | Execuções › Execução `{id}` | origem registrada ou dashboard |
| `/workorders/:id` | Consulta › Workorder `{id}` | `/search` com query anterior |
| `/lots/:id` | Consulta › Lote `{id}` | `/search` com query anterior |
| `/serials/:id` | Consulta › Serial `{id}` | `/search` com query anterior |
| `/pending-items/:id` | Pendências › Pendência `{id}` | lista com filtros anteriores |

O retorno deve usar estado serializado e validado na URL, nunca depender apenas
do histórico do navegador. Valores de `from` só podem apontar para rotas
internas conhecidas.

## Estados obrigatórios

| Estado | Representação |
| --- | --- |
| `loading` | estrutura reservada, ação duplicada bloqueada e rótulo acessível |
| `empty` | consulta concluída sem itens; não é erro nem zero inferido |
| `partial` | conteúdo utilizável com fonte ou processamento incompleto |
| `stale` | dados válidos com horário de referência antigo explícito |
| `error` | falha de contrato ou operação com ação segura de correção |
| `forbidden` | sessão válida sem permissão; não tenta refresh repetido |
| `unavailable` | API ou dependência temporariamente indisponível, com nova tentativa |

`404` fora do escopo não revela existência. `409` preserva conflito e oferece
recarga; `422` associa erros aos campos; erros `5xx` nunca exibem stack trace,
SQL, token ou caminho interno.

## Estado na URL

- Dashboard: organização e período.
- Execução: aba, paginação, fonte, severidade e ordenação.
- Consulta: tipo, texto, paginação e ordenação quando suportadas pelo contrato.
- Pendências: estado, categoria, prioridade, área, Workorder, paginação e ordem.
- Administração: seção, busca e paginação.
- Perfil: seção ativa.

Preferências puramente visuais, como tema e densidade, pertencem ao perfil ou
armazenamento local não sensível e não poluem a URL.

## Estrutura e ownership

```text
web/src/app/
├── core/                 sessão, guards, interceptor e configuração
├── layout/               shell, menu, cabeçalho e breadcrumbs          #56
├── shared/
│   ├── api/              cliente, modelos e envelope de erro            #56
│   ├── ui/               estados e componentes sem regra de negócio     #56
│   └── i18n/             catálogos, locale e formatação                 #57
└── domains/
    ├── imports/          upload e acompanhamento inicial                #58
    ├── executions/       detalhe, histórico e evidências                #59
    ├── dashboard/        indicadores operacionais                       #60
    ├── queries/          busca e detalhes de entidades                  #61
    ├── pending/          fila e detalhe                                 #62
    ├── profile/          perfil e preferências                          #44
    └── admin/            identidades e acesso                           #44
```

Somente a #56 altera inicialmente `app.routes.ts`, shell, estilos globais e o
cliente compartilhado. Issues de domínio registram rotas filhas e não colocam
regras em `shared/`. A #57 é proprietária dos catálogos e da validação de
chaves. Mudança concorrente em arquivo compartilhado exige combinação prévia.

## Decisões e lacunas

| ID | Diferença | Decisão | Destino |
| --- | --- | --- | --- |
| WEB-G01 | protótipo usa dados fixos e ações locais | remover; produção usa API real | #56–#62 |
| WEB-G02 | monitor simula lista global de execuções, mas não há `GET /executions` | adaptar para localização/detalhe; novo endpoint exige contrato aprovado | #59 |
| WEB-G03 | busca exibe coleção, mas API atual consulta identificador exato | adaptar para busca exata; paginação geral depende de extensão contratual | #61 |
| WEB-G04 | protótipo aprova, rejeita, atribui e altera responsável | remover da Etapa 3 | Etapa 4 — decisão humana |
| WEB-G05 | catálogo, geração e exportação de relatórios não possuem API | adiar e retirar do menu | Etapa 4 — relatórios |
| WEB-G06 | notificações e e-mail são apenas apresentação | remover da Etapa 3 | Etapa 4 — notificações/SMTP |
| WEB-G07 | parâmetros operacionais aparecem em configurações | remover até existir contrato e autorização específicos | etapa futura |
| WEB-G08 | configuração pessoal do protótipo se sobrepõe ao perfil existente | adaptar para `/profile`; manter apenas preferências suportadas | #56/#57 |
| WEB-G09 | protótipo não possui login, upload ou administração real | implementar com contratos existentes | #56/#58 e #44 |
| WEB-G10 | organização sintética era filtro livre no navegador | adaptar ao escopo efetivo; filtro só estreita concessões | #56–#62 |

## Modo TV

O Modo TV é **adiado**. Ele não é necessário para o fluxo login → upload →
execução → consulta → pendência, não possui requisito de autorização próprio e
ampliaria o escopo de responsividade, atualização e acessibilidade. A #56 deve
preservar componentes capazes de compor painéis, mas não oferecer botão ou
preferência de Modo TV. Uma issue futura deverá definir páginas permitidas,
atualização, proteção contra exposição e aceite do PO.

## Revisão humana

Antes do merge, o PO e ao menos um responsável técnico devem registrar no PR:

- aceite das rotas e decisões `WEB-G01` a `WEB-G10`;
- concordância com o adiamento de relatórios, decisão humana e Modo TV;
- confirmação de que o protótipo continua referência funcional congelada.
