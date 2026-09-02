# Fundação visual e técnica da aplicação web

## Origem e autorização

Os ativos foram incorporados da tag imutável `prototype-v1.0`, diretório
`assets/`, mantido pelo projeto como referência aprovada. A aplicação publica
uma cópia própria em `web/public/assets` e não depende da branch do protótipo em
build ou execução. Não foram incorporados dados, HTML, JavaScript ou CSS do
protótipo.

## Tokens

`web/src/styles.css` é a fonte dos tokens semânticos. Cores representam fundo,
superfície, texto, borda, marca, foco, sucesso, informação, alerta, erro,
parcialidade e indisponibilidade nos temas claro e escuro. Espaçamento segue a
escala de 4, 8, 12, 16, 24 e 32 px; controles têm ao menos 44 px. Raios,
elevação e movimento também são tokens. `prefers-reduced-motion` reduz todas as
transições.

LGEI é usada em conteúdo e títulos; JetBrains Mono fica reservada a
identificadores e valores técnicos. Todas possuem fallback de sistema.

## Marca

| Contexto | Variante |
| --- | --- |
| superfície clara | `logo-horizontal.png` |
| superfície escura | `logo-negativa-horizontal.png` |
| espaço reduzido | `simbolo.png` ou `simbolo-negativo.png` |

Logos usam `object-fit: contain`, preservando proporção, e não recebem filtros
ou recoloração. Ícones monocromáticos podem herdar contraste do shell.

## Estrutura e contratos

- `core/`: sessão, guards e interceptor de autenticação;
- `layout/`: shell raiz e navegação;
- `shared/api/`: erros, tipos e serialização HTTP sem regras de domínio;
- `shared/i18n/`: catálogos, preferência ativa e formatadores localizados;
- `shared/ui/`: componentes visuais sem regras de negócio;
- `features/`: telas existentes, migradas progressivamente para domínios.

O access token permanece apenas no sinal em memória do `SessionService`; o
refresh usa cookie protegido. O cliente nunca acessa banco ou caminhos internos.
`ApiFailure` diferencia 401, 403, 404, 409, 422 e indisponibilidade, preserva o
correlation ID e substitui detalhes internos em falhas 5xx.

## Catálogo

Administradores encontram o catálogo interno na área de administração. Ele usa
dados sintéticos, demonstra superfícies, badge e estados parcial, proibido e
indisponível e declara explicitamente que não é uma tela operacional.

Botão, campo, seletor, confirmação, modal, tabela e paginação possuem contratos
compartilhados em `shared/ui`. Jornadas planejadas só entram no menu quando a
respectiva rota estiver implementada; uma permissão futura não cria um link que
redireciona silenciosamente para o perfil.

## Diferenças intencionais do protótipo

- navegação deriva das permissões efetivas de `/me`;
- Relatórios e Modo TV não aparecem na Etapa 3;
- menu móvel, skip link e foco visível ampliam a acessibilidade;
- tokens semânticos substituem cores e espaçamentos específicos por página;
- ações simuladas não foram copiadas.

## Internacionalização e acessibilidade

Textos de produto e nomes acessíveis usam os catálogos `pt-BR` e `en-US`.
Datas, números e quantidades seguem o locale ativo, enquanto datas e horas
também respeitam o timezone do perfil. O processo para criar chaves e os
contratos de foco, teclado e mensagens de validação estão documentados em
[web-internationalization-accessibility.md](web-internationalization-accessibility.md).
