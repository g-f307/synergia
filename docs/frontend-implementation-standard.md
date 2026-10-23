# Norma de implementação visual do frontend

## Status e aplicação

Este documento é **normativo**. Toda tela nova e toda alteração visual na
aplicação Angular deve obedecê-lo. Ele complementa o
[design system](web-design-system.md) e as regras de
[internacionalização e acessibilidade](web-internationalization-accessibility.md).

Uma divergência só pode ser aceita quando:

1. houver uma necessidade funcional ou de acessibilidade demonstrável;
2. a justificativa estiver registrada na issue e no pull request;
3. o impacto sobre as demais telas tiver sido avaliado; e
4. a exceção tiver sido aprovada na revisão.

Preferências pessoais, conveniência de implementação ou fidelidade a um
mockup antigo não justificam quebrar o padrão vigente.

## Princípios obrigatórios

- Reutilize tokens, componentes e padrões existentes antes de criar uma
  variante local.
- Preserve a hierarquia visual e funcional já consolidada nas telas
  equivalentes. Não redesenhe cada rota de forma independente.
- Remova informação redundante. Um título, breadcrumb, badge ou texto de apoio
  deve existir apenas quando acrescentar contexto ou orientar uma ação.
- Priorize leitura rápida, ações claras e densidade adequada para uso
  operacional. Evite parágrafos explicativos que o usuário precise reler.
- Dados, permissões e estados reais têm precedência sobre elementos
  decorativos. Não invente métricas, estados, gráficos ou capacidades.
- A interface deve funcionar nos temas claro e escuro, em desktop e em tela
  estreita, com teclado, zoom e conteúdo longo.

## Shell e área de conteúdo

- O shell autenticado é uma moldura única formada por sidebar, topbar e área
  principal. Seu tamanho, escala, raios e espaçamentos não variam por rota.
- A sidebar e a topbar permanecem fixas. O scroll vertical deve ocorrer dentro
  do contêiner principal da tela, nunca no documento ou na moldura externa.
- A sidebar pode ser expandida, compactada ou transformada em drawer nos
  breakpoints existentes. A marca deve permanecer legível e sem sobreposição;
  o controle de recolhimento mantém a posição definida no rodapé.
- A topbar identifica a área atual à esquerda e mantém notificações, tema e
  saída alinhados à direita. Os três controles usam o mesmo tratamento visual,
  dimensão e estado de interação.
- O contêiner principal usa a superfície, borda, raio e espaçamento já
  definidos. Evite criar caixas dentro de caixas sem necessidade semântica.
- Use `height: 100%`, `min-height: 0` e `overflow-y: auto` na cadeia necessária
  para preservar o scroll interno. Listas nunca podem ser cortadas antes da
  paginação.

As referências estruturais vigentes são `web/src/app/app.component.*`,
`web/src/styles.css` e as telas de catálogo de execuções e pendências.

## Cabeçalhos, navegação e hierarquia

- Cada tela possui uma única identidade principal: título curto, descrição
  opcional e ações primárias relacionadas à página.
- Em telas de lista, a ordem preferencial é: cabeçalho, divisor quando
  necessário, filtros, identificação dos resultados, lista e paginação.
- Em telas de detalhe, o botão de voltar fica à esquerda e usa o mesmo estilo
  das demais telas de detalhe. O título vem logo após ou abaixo dele conforme o
  espaço disponível.
- A identificação da topbar para subtelas segue o formato
  `Recurso / identificador`. Não duplique essa informação com um breadcrumb
  `Início > Recurso > identificador` dentro do conteúdo.
- Não use simultaneamente badge, breadcrumb e título para comunicar a mesma
  rota. Preserve apenas os elementos que ajudam o usuário a se localizar.
- Títulos, subtítulos, rótulos, ajuda e valores técnicos devem usar a escala
  tipográfica compartilhada. Não introduza tamanhos arbitrários por componente.
- LGEI é a fonte de interface; JetBrains Mono é reservada para IDs, hashes,
  códigos e outros valores técnicos.

## Filtros, listas e paginação

- Filtros extensos usam o painel recolhível já adotado, com acionador compacto.
  Filtros simples podem permanecer abertos quando isso reduzir etapas.
- O título e a contagem dos resultados aparecem antes da lista e seguem o mesmo
  formato das telas equivalentes. Exiba data de atualização apenas quando ela
  for relevante e confiável.
- Abrir filtros não pode fixar o painel nem reduzir a lista a uma área de scroll
  impraticável. Filtros e resultados participam do mesmo fluxo do contêiner.
- A paginação aparece uma única vez, permanece visível após a lista e não pode
  ser confundida com breadcrumb ou identificação de rota.
- Linhas de listagem precisam funcionar com textos e identificadores longos.
  Defina conscientemente quebra, truncamento ou expansão; nunca deixe texto
  ultrapassar a moldura.
- Em CRUDs, prefira ações por ícones consistentes para editar, ativar ou
  desativar, sempre com nome acessível e dica textual. Não use ícones genéricos
  quando houver um símbolo específico para o domínio.

## Cards, cores, estados e gráficos

- O bordô do SYNERGIA é cor de marca e de ação. Não o use como única cor de
  séries, métricas ou estados.
- Sucesso, informação, atenção, parcialidade e erro usam os tokens semânticos
  existentes. Cor nunca é o único meio de comunicar um estado.
- Gráficos devem responder a uma pergunta operacional e usar cores intuitivas,
  legenda, rótulos e alternativa textual. Não inclua gráfico apenas para
  preencher espaço.
- Badges e cards devem manter contraste e significado nos dois temas. Badges
  de métricas estruturais seguem a identidade do sistema; badges de estado
  seguem o estado semântico.
- Use `syn-state` e os componentes compartilhados para carregamento, vazio,
  falha, acesso proibido e indisponibilidade.
- Banners são reservados a informação atual, acionável e relevante para a
  decisão do usuário. Não exiba alertas genéricos, permanentes ou repetidos no
  conteúdo da própria tela.

## Formulários e modais

- Formulários seguem a sequência: identidade da tela, seções de campos,
  controle de alteração quando aplicável e ações finais.
- Campos equivalentes usam largura, altura e espaçamento consistentes. Uma
  composição não deve parecer formada por contêineres de tamanhos aleatórios.
- A ação principal de salvar fica no rodapé ou abaixo do conjunto completo de
  campos. Não a posicione ao lado de um único campo de modo que pareça persistir
  apenas aquele valor.
- Em operações auditáveis, o título e a explicação de “Controle da alteração”
  aparecem antes do campo de motivo.
- Use os componentes compartilhados de modal e confirmação. Não use
  `window.alert`, `window.confirm` ou diálogos nativos do navegador.
- Modais devem fechar pelo botão explícito, por `Escape` e, quando não houver
  risco de perda silenciosa, por clique no backdrop. O foco entra no modal,
  permanece contido e retorna ao acionador ao fechar.
- Ações destrutivas informam objeto, consequência e motivo exigido. Cancelar é
  sempre possível e não altera dados.

## Conteúdo, internacionalização e ativos

- Todo texto de produto entra nos catálogos `pt-BR` e `en-US`; não espalhe
  strings traduzíveis nos componentes.
- Textos são objetivos, consistentes e orientados à tarefa. Evite nomenclaturas
  redundantes, jargão interno e explicações que não mudam a decisão do usuário.
- Ícones e logos autorizados ficam em `web/public/assets`. Não dependa de ativos
  copiados de sites de referência ou de diretórios locais ignorados pelo Git.
- Logos preservam proporção e não recebem recoloração improvisada. Ícones
  monocromáticos devem usar a cor da interface ou a cor oficial definida no
  design system.
- Elementos decorativos usam texto alternativo vazio. Controles com ícone
  recebem nome acessível explícito.

## Acessibilidade e responsividade

- Controles interativos devem ter área mínima de 44 px, foco visível, ordem de
  teclado previsível e estado desabilitado distinguível.
- O contraste deve atender WCAG AA nos temas claro e escuro, inclusive em
  hover, foco, seleção, erro e desabilitado.
- O hover nunca pode tornar texto ilegível. Mudanças de cor devem preservar a
  relação entre texto, ícone, fundo e borda.
- Labels permanecem associados aos campos; erros usam `aria-invalid` e
  `aria-describedby`; atualizações assíncronas relevantes usam `status` ou
  `alert`.
- Tabelas e abas extensas precisam de comportamento móvel deliberado. Prefira
  empilhamento ou scroll horizontal identificado a cortes de conteúdo.
- Respeite `prefers-reduced-motion` e não dependa de animação para compreensão.

## Processo obrigatório para uma tela

Antes de implementar:

1. classifique a tela como lista, detalhe, formulário, dashboard ou modal;
2. localize uma tela já concluída da mesma categoria;
3. identifique componentes, tokens e padrões que podem ser reutilizados;
4. registre na issue qualquer desvio necessário antes de codificá-lo.

Durante a implementação:

1. preserve o shell e o scroll interno;
2. use tokens e catálogos de tradução;
3. trate carregamento, vazio, erro, conteúdo longo e permissões;
4. valide tema claro, tema escuro e responsividade;
5. adicione ou atualize testes do comportamento alterado.

## Checklist de aceite do pull request

Toda mudança visual deve declarar no PR os itens aplicáveis:

- [ ] usei uma tela equivalente como referência e informei qual;
- [ ] não dupliquei título, badge, breadcrumb ou paginação;
- [ ] preservei o shell, as dimensões do contêiner e o scroll interno;
- [ ] reutilizei tokens e componentes compartilhados;
- [ ] validei conteúdo vazio, preenchido, longo, erro e carregamento;
- [ ] validei tema claro e escuro;
- [ ] validei desktop e viewport estreito;
- [ ] validei teclado, foco, nomes acessíveis e contraste;
- [ ] atualizei `pt-BR` e `en-US` quando acrescentei texto;
- [ ] não introduzi ativos externos, dados reais ou capacidades inexistentes;
- [ ] executei os testes, lint, build e validações visuais aplicáveis;
- [ ] documentei e justifiquei qualquer exceção a esta norma.

Comandos mínimos para mudanças no frontend:

```bash
python scripts/validate_visual_system.py
python scripts/validate_i18n.py
cd web
npm run lint
npm test -- --watch=false
npm run build
```

Mudanças no shell, navegação, permissões ou jornadas críticas também exigem o
E2E aplicável com `npm run e2e`. A revisão visual deve usar dados sintéticos e
incluir pelo menos os dois temas e um viewport estreito.
