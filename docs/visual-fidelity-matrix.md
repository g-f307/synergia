# Matriz de fidelidade visual

Referência congelada: `prototype-pages` / `prototype-v1.0`. A comparação usa a
composição e os ativos do protótipo, sem importar `data.js`, JavaScript simulado
ou capacidades sem contrato.

## Fundação compartilhada

| Elemento | Referência | Implementação Angular | Resultado |
| --- | --- | --- | --- |
| Marca | logo horizontal na sidebar | mesmo ativo em desktop e símbolo oficial na sidebar compacta | equivalente |
| Tipografia | LGEI Headline, LGEI Text e JetBrains Mono | arquivos oficiais locais, com fallback de sistema | equivalente |
| Cores | bordô `#A50034`, superfícies claras e estados semânticos | tokens `--syn-*` extraídos do CSS congelado | equivalente |
| Shell | sidebar branca, cabeçalho de 72 px e conteúdo cinza | mesma grade e dimensões; menu condicionado por permissão | equivalente |
| Responsividade | sidebar completa, compacta e drawer móvel | `>1365`, `1024–1365`, `<1024` e ajustes `<768` | equivalente |
| Componentes | cards, badges, filtros, tabelas, alertas e modais | estilos compartilhados e variantes semânticas acessíveis | equivalente |

## Telas existentes

| Tela Angular | Página de referência | Desktop | Móvel | Diferença justificada |
| --- | --- | --- | --- | --- |
| `/login` | identidade geral do protótipo | painel de marca e formulário em superfície branca | somente formulário e marca, sem painel decorativo | login não existe no protótipo; composição deriva dos mesmos ativos e tokens |
| `/profile` | `configuracoes.html` | cabeçalho, card de preferências e painel de avatar | coluna única com controles de 44 px | somente preferências persistidas por `/me`; TV e parâmetros simulados não são exibidos |
| `/admin` | shell e catálogo visual | cards de recursos e catálogo de variantes | grade em coluna única | administração não possui página no protótipo; contratos reais permanecem soberanos |
| `/imports/new` | shell e formulários | formulário e orientação em grade | blocos empilhados | upload real substitui ações demonstrativas inexistentes |
| `/imports/:id` | estados e cards | resumo, inspeções e contagens | coluna única | conteúdo vem exclusivamente das APIs persistidas |
| `/executions` | `monitor.html` | localização por ID dentro do shell oficial | formulário compacto | não existe `GET /executions`; lista sintética não foi copiada |
| `/executions/:id` | `monitor.html` | KPIs, abas, filtros, estados e ações | abas roláveis e cards empilhados | detalhe real substitui modal e logs sintéticos do protótipo |

## Evidência automatizada

`scripts/validate_visual_system.py` verifica tokens, ativos, contraste WCAG AA,
breakpoints e ausência de dependência do runtime congelado. A suíte Angular
cobre shell autenticado, drawer móvel, foco, modal, componentes semânticos,
guards, permissões e os fluxos funcionais remodelados.

Capturas reproduzíveis da jornada pública, sem credenciais ou respostas reais:

- [login desktop, 1440 × 1000](evidence/issue-69-login-desktop.png);
- [login móvel, 390 × 844](evidence/issue-69-login-mobile.png).

As telas autenticadas devem ser recapturadas no ambiente de homologação com
dados sintéticos autorizados. Credenciais, tokens e respostas reais não são
versionados. Um vídeo não faz parte do repositório para evitar a publicação
acidental de identidade ou dados de sessão; a regressão verificável é mantida
pelos testes e pelas capturas versionadas acima.
