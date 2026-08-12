# SYNERGIA — protótipo navegável

Protótipo frontend da solução SYNERGIA para validação de fluxos, conteúdo e interface. Todos os registros são sintéticos, permanecem no navegador e não representam informações operacionais reais.

## Execução

Não há build nem dependências de execução. A partir da pasta `synergia`, use uma das opções:

```bash
python3 -m http.server 8000
```

Depois, acesse `http://localhost:8000`. Também é possível abrir `index.html` diretamente, embora um servidor local produza comportamento mais próximo de uma implantação web.

## Telas e fluxos

- `index.html`: visão geral, indicadores, fontes, prioridades e execução manual simulada;
- `consulta.html`: busca efetiva nos dados sintéticos por Workorder, lote ou serial;
- `monitor.html`: execuções, filtros, logs, tentativas e reprocessamento simulado;
- `pendencias.html`: fila filtrável, paginação e seleção acessível;
- `detalhe-pendencia.html`: contexto rastreável, histórico, área responsável e ações simuladas;
- `relatorios.html`: catálogo filtrável, estados, histórico e exportação simulada;
- `visualizar-relatorio.html`: resumo, Workorders, sumário OQC e prioridades;
- `configuracoes.html`: preferências locais de tema, densidade, fonte, atualização e Modo TV.

Parâmetros como `?wo=WO-10293`, `?id=P-0035`, `?id=EX-20260731-006` e `?id=REL-20260731-01` permitem abrir diretamente um registro relacionado.

## Modo TV

O botão de TV ativa uma apresentação de tela cheia, sem rolagem e com alternância automática entre painéis. Os controles não essenciais são removidos, as informações críticas são ampliadas e o ciclo pausa temporariamente quando há interação. A preferência fica armazenada no navegador.

As páginas com conteúdo operacional próprio apresentam painéis dedicados. Caso o Modo TV seja solicitado em uma página sem painel apropriado, o protótipo abre o Dashboard com segurança em vez de apresentar uma tela vazia.

## Acessibilidade e responsividade

- modos claro e escuro, com detecção da preferência do sistema;
- navegação por teclado e foco visível;
- link para pular ao conteúdo;
- labels associados aos controles;
- modais com gerenciamento de foco e fechamento por `Escape`;
- estados comunicados por texto, ícone e cor;
- suporte a `prefers-reduced-motion`;
- reorganização de cards, filtros e tabelas para desktop, tablet e celular;
- tipografia LGEI e JetBrains Mono fornecida localmente.

## Dados e segurança

`data.js` contém somente exemplos sintéticos. O protótipo:

- não possui backend;
- não chama APIs ou serviços externos;
- não contém credenciais, tokens ou dados pessoais;
- não envia e-mails, mensagens ou arquivos;
- não executa decisões automáticas;
- não utiliza inteligência artificial;
- não altera sistemas de origem.

Exportação, reprocessamento, execução sob demanda e mudança de responsável são demonstrações locais. A interface informa explicitamente essas simulações.

## Estrutura

- `styles.css`: design system, temas, responsividade e Modo TV;
- `script.js`: navegação, ícones, preferências, modais, paginação e utilitários;
- `data.js`: conjunto sintético compartilhado;
- `assets/`: fontes, assinaturas e iconografia oficial;
- `tests/smoke_ui.py`: verificação opcional de renderização, console, imagens, acessibilidade básica, overflow e fluxos funcionais.

## Validação opcional

Com Python, Selenium, Chromium e ChromeDriver disponíveis:

```bash
python3 tests/smoke_ui.py
```

O teste renderiza todas as páginas em desktop e celular, verifica o Modo TV entre 1920×1080 e 1024×640 — incluindo larguras equivalentes a zoom elevado —, exercita oito fluxos centrais e mede marca/contraste nos temas claro e escuro. As capturas são gravadas em `/tmp/synergia-ui-smoke`.

## Limitações deliberadas

- persistência limitada ao `localStorage` do navegador;
- exportações geram apenas confirmação visual;
- logs e evidências são representações sintéticas;
- integrações corporativas, autenticação e permissões reais dependem da implementação futura;
- os resultados devem continuar sujeitos à revisão humana.
