# Internacionalização e acessibilidade da aplicação web

## Idiomas e preferência

A aplicação oferece `pt-BR` e `en-US`. O idioma vem do perfil retornado por
`/me` e é reaplicado após autenticação, renovação da sessão e atualização do
perfil. Valores ausentes ou ainda não suportados usam `pt-BR` como fallback
seguro. A escolha permanece no servidor; o navegador não mantém uma segunda
fonte de verdade.

Antes da autenticação, a tela de login oferece um seletor de idioma em memória.
Uma tentativa rejeitada preserva essa escolha para que o erro e uma nova
tentativa continuem no idioma selecionado. Após autenticação, o locale do
perfil reassume a autoridade; logout e expiração retornam ao fallback, mantendo
o seletor disponível para a próxima sessão anônima.

`I18nService` atualiza o atributo `lang` do documento e centraliza textos e
formatação. Datas e horas usam também o timezone do perfil. Números e
quantidades usam `Intl`; valores ausentes continuam distintos de zero.

## Catálogos e novas chaves

Os catálogos ficam em `web/src/app/shared/i18n/catalogs`. Para acrescentar
texto de produto:

1. crie uma chave semântica e estável, agrupada por domínio;
2. inclua a mesma chave em `pt-BR.json` e `en-US.json`;
3. consuma-a por `I18nService.t`, sem espalhar texto traduzível no componente;
4. use parâmetros nomeados para valores dinâmicos;
5. execute `python scripts/validate_i18n.py` e os testes do frontend.

O validador executado na CI rejeita catálogos com chaves ausentes, excedentes,
vazias ou órfãs. A tipagem de `TranslationKey` detecta referências inválidas na
compilação. Códigos de erro da API permanecem estáveis e independentes do texto
apresentado ao usuário.

## Regras básicas de acessibilidade

- preserve os landmarks do shell e mantenha o conteúdo principal focável;
- após navegação, mova o foco para `main`; o skip link oferece o mesmo destino;
- todo controle precisa de nome acessível e erros de campo devem usar
  `aria-invalid` e `aria-describedby`;
- modais recebem foco inicial, contêm a navegação por `Tab`, fecham com `Escape`
  e devolvem o foco ao elemento anterior;
- menus fecham com `Escape` e devolvem o foco ao acionador;
- estados assíncronos relevantes usam regiões `status` ou `alert`;
- não comunique estado somente por cor e respeite `prefers-reduced-motion`.

Testes de teclado e foco devem acompanhar alterações nesses contratos. A
tradução integral da documentação e novos idiomas não fazem parte desta etapa.
